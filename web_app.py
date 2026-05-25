#!/usr/bin/env python3
"""Local web UI for generating Manim teaching videos from problem images.

The server intentionally uses only Python standard-library modules. It serves
the static frontend, accepts image uploads, starts solve_image_to_video.py as a
background job, and exposes status/video/chat endpoints for the UI.
"""

from __future__ import annotations

import argparse
import cgi
import json
import mimetypes
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
SCRIPT_PATH = ROOT / "solve_image_to_video.py"
RUNS_ROOT = ROOT / "runs" / "web_jobs"
ARTIFACT_NAMES = {
    "transcript_prompt.md",
    "transcript_generation.json",
    "transcript_model_response.json",
    "transcript_raw_model_output.txt",
    "transcript_api_error.txt",
    "solution_prompt.md",
    "code_prompt_preview.md",
    "solution_generation.json",
    "solution_model_response.json",
    "solution_raw_model_output.txt",
    "solution_api_error.txt",
    "code_prompt.md",
    "code_generation.json",
    "code_model_response.json",
    "code_raw_model_output.txt",
    "code_api_error.txt",
    "prompt.md",
    "run_config.json",
    "problem_transcript.md",
    "solution.md",
    "lecture_script.md",
    "scenes.md",
    "render_notes.md",
    "generation.json",
    "video_scene.py",
    "validation_warnings.txt",
    "render.log",
    "api_error.txt",
}
ARTIFACT_PATTERNS = [
    re.compile(r"repair_\d+_(?:response|invalid)\.json$"),
    re.compile(r"repair_\d+_(?:summary|api_error|raw_output)\.(?:md|txt)$"),
    re.compile(r"render_repair_\d+\.log$"),
]


JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_slug(value: str, fallback: str = "job") -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return slug[:72] or fallback


def read_text(path: Path, limit: Optional[int] = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if limit and len(text) > limit:
        return text[-limit:]
    return text


def write_json_response(handler: "AppHandler", payload: Dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def write_text_response(handler: "AppHandler", text: str, status: int = 200, content_type: str = "text/plain") -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def guess_upload_suffix(filename: str, content_type: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return suffix
    guessed = mimetypes.guess_extension(content_type or "")
    if guessed in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return guessed
    return ".png"


def newest_mp4(out_dir: Path) -> Optional[Path]:
    video_path_txt = out_dir / "video_path.txt"
    if video_path_txt.exists():
        recorded = Path(read_text(video_path_txt).strip())
        if recorded.exists() and recorded.suffix.lower() == ".mp4":
            return recorded

    media_dir = out_dir / "media" / "videos"
    if not media_dir.exists():
        return None
    candidates = list(media_dir.rglob("*.mp4"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def is_allowed_artifact(name: str) -> bool:
    return name in ARTIFACT_NAMES or any(pattern.fullmatch(name) for pattern in ARTIFACT_PATTERNS)


def list_artifacts(out_dir: Path) -> list[str]:
    if not out_dir.exists():
        return []
    artifacts = []
    for path in out_dir.iterdir():
        if path.is_file() and is_allowed_artifact(path.name):
            artifacts.append(path.name)
    return sorted(artifacts)


def job_snapshot(job_id: str) -> Dict[str, Any]:
    with JOBS_LOCK:
        job = dict(JOBS.get(job_id) or {})
    if not job:
        return {}

    out_dir = Path(job["out_dir"])
    return_code = job.get("return_code")
    video_path = newest_mp4(out_dir)
    artifacts = list_artifacts(out_dir)

    status = job.get("status", "queued")
    if return_code == 0:
        status = "done"
    elif return_code not in {None, 0}:
        status = "error"

    progress = 8
    stage = "等待启动"
    if (out_dir / "prompt.md").exists():
        progress, stage = 18, "已创建提示词"
    if (out_dir / "transcript_generation.json").exists() or (out_dir / "problem_transcript.md").exists():
        progress, stage = 35, "已完成题面转写"
    if (out_dir / "solution_generation.json").exists():
        progress, stage = 52, "已完成解题与分镜"
    if (out_dir / "code_prompt.md").exists():
        progress, stage = 60, "正在生成 Manim 代码"
    if (out_dir / "code_generation.json").exists():
        progress, stage = 68, "已生成 Manim 代码"
    if (out_dir / "video_scene.py").exists():
        progress, stage = 72, "已写出 Manim 场景"
    if (out_dir / "render.log").exists():
        progress, stage = 82, "正在渲染或修复"
    if video_path:
        progress, stage = 100, "视频已生成"
    if status == "error":
        progress = min(progress, 96)
        stage = "任务失败"
    log_tail = ""
    log_path = Path(job.get("process_log", ""))
    if log_path.exists():
        log_tail = read_text(log_path, limit=6000)
    elif (out_dir / "render.log").exists():
        log_tail = read_text(out_dir / "render.log", limit=6000)

    snapshot = {
        "id": job_id,
        "status": status,
        "stage": stage,
        "progress": progress,
        "createdAt": job.get("created_at"),
        "startedAt": job.get("started_at"),
        "finishedAt": job.get("finished_at"),
        "returnCode": return_code,
        "outDir": str(out_dir),
        "imageName": job.get("image_name"),
        "quality": job.get("quality"),
        "inputMode": job.get("input_mode"),
        "artifacts": artifacts,
        "hasVideo": bool(video_path),
        "videoUrl": f"/api/jobs/{job_id}/video" if video_path else None,
        "imageUrl": f"/api/jobs/{job_id}/image",
        "logTail": log_tail,
    }
    if status != job.get("status"):
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = status
    return snapshot


def wait_for_process(job_id: str, process: subprocess.Popen[str]) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["status"] = "running"
            JOBS[job_id]["started_at"] = utc_timestamp()
            JOBS[job_id]["stage"] = "后端生成中"
            JOBS[job_id]["pid"] = process.pid
    return_code = process.wait()
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["return_code"] = return_code
            JOBS[job_id]["finished_at"] = utc_timestamp()
            JOBS[job_id]["status"] = "done" if return_code == 0 else "error"
            JOBS[job_id]["stage"] = "视频已生成" if return_code == 0 else "任务失败"


def build_job_command(job: Dict[str, Any]) -> list[str]:
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        str(job["upload_path"]),
        "--out-dir",
        str(job["out_dir"]),
        "--quality",
        job["quality"],
        "--input-mode",
        job["input_mode"],
        "--json-mode",
        job["json_mode"],
        "--max-repair-attempts",
        job["max_repair_attempts"],
    ]
    if job.get("problem_text_file"):
        cmd.extend(["--problem-text-file", str(job["problem_text_file"])])
    if job.get("model"):
        cmd.extend(["--model", job["model"]])
    if job.get("base_url"):
        cmd.extend(["--base-url", job["base_url"]])
    if job.get("api_url"):
        cmd.extend(["--api-url", job["api_url"]])
    if job.get("api_style"):
        cmd.extend(["--api-style", job["api_style"]])
    if job.get("api_key_env"):
        cmd.extend(["--api-key-env", job["api_key_env"]])
    if job.get("vision_model"):
        cmd.extend(["--vision-model", job["vision_model"]])
    if job.get("vision_base_url"):
        cmd.extend(["--vision-base-url", job["vision_base_url"]])
    if job.get("vision_api_url"):
        cmd.extend(["--vision-api-url", job["vision_api_url"]])
    if job.get("vision_api_style"):
        cmd.extend(["--vision-api-style", job["vision_api_style"]])
    if job.get("vision_api_key_env"):
        cmd.extend(["--vision-api-key-env", job["vision_api_key_env"]])
    if job.get("vision_json_mode"):
        cmd.extend(["--vision-json-mode", job["vision_json_mode"]])
    if job.get("prefer_vision_over_text") is False:
        cmd.append("--no-prefer-vision-over-text")
    if job.get("no_render"):
        cmd.append("--no-render")
    if job.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def start_generation_job(fields: Dict[str, Any]) -> Dict[str, Any]:
    upload = fields["image"]
    original_name = upload.filename or "problem.png"
    suffix = guess_upload_suffix(original_name, upload.type or "")
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    name_slug = safe_slug(Path(original_name).stem, "problem")
    job_dir = RUNS_ROOT / f"{job_id}-{name_slug}"
    upload_dir = job_dir / "upload"
    out_dir = job_dir / "output"
    upload_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    upload_path = upload_dir / f"source{suffix}"
    with upload_path.open("wb") as destination:
        shutil.copyfileobj(upload.file, destination)

    problem_text = (fields.get("problemText") or "").strip()
    problem_text_file = None
    if problem_text:
        problem_text_file = upload_dir / "problem.txt"
        problem_text_file.write_text(problem_text + "\n", encoding="utf-8")

    quality = fields.get("quality") or "m"
    if quality not in {"l", "m", "h", "k", "-ql", "-qm", "-qh", "-qk"}:
        quality = "m"
    input_mode = fields.get("inputMode") or "auto"
    if input_mode not in {"auto", "image", "text"}:
        input_mode = "auto"
    json_mode = fields.get("jsonMode") or "json_object"
    if json_mode not in {"schema", "json_object", "none"}:
        json_mode = "json_object"
    api_style = fields.get("apiStyle") or ""
    if api_style and api_style not in {"chat", "responses"}:
        api_style = ""
    vision_api_style = fields.get("visionApiStyle") or ""
    if vision_api_style and vision_api_style not in {"chat", "responses"}:
        vision_api_style = ""
    vision_json_mode = fields.get("visionJsonMode") or ""
    if vision_json_mode and vision_json_mode not in {"schema", "json_object", "none"}:
        vision_json_mode = ""

    max_repair_attempts = fields.get("maxRepairAttempts") or "2"
    if not re.fullmatch(r"\d{1,2}", str(max_repair_attempts)):
        max_repair_attempts = "2"

    job = {
        "id": job_id,
        "created_at": utc_timestamp(),
        "status": "queued",
        "stage": "等待启动",
        "image_name": original_name,
        "upload_path": str(upload_path),
        "out_dir": str(out_dir),
        "process_log": str(job_dir / "process.log"),
        "quality": quality,
        "input_mode": input_mode,
        "json_mode": json_mode,
        "max_repair_attempts": str(max_repair_attempts),
        "problem_text_file": str(problem_text_file) if problem_text_file else "",
        "model": (fields.get("model") or "").strip(),
        "base_url": (fields.get("baseUrl") or "").strip(),
        "api_url": (fields.get("apiUrl") or fields.get("codeApiUrl") or "").strip(),
        "api_style": api_style,
        "api_key_env": (fields.get("apiKeyEnv") or "").strip(),
        "vision_model": (fields.get("visionModel") or "").strip(),
        "vision_base_url": (fields.get("visionBaseUrl") or "").strip(),
        "vision_api_url": (fields.get("visionApiUrl") or "").strip(),
        "vision_api_style": vision_api_style,
        "vision_api_key_env": (fields.get("visionApiKeyEnv") or "").strip(),
        "vision_json_mode": vision_json_mode,
        "prefer_vision_over_text": fields.get("preferVisionOverText", "true") != "false",
        "no_render": fields.get("noRender") == "true",
        "dry_run": fields.get("dryRun") == "true",
        "return_code": None,
        "pid": None,
    }
    cmd = build_job_command(job)
    job["command"] = cmd

    with JOBS_LOCK:
        JOBS[job_id] = job

    log_file = Path(job["process_log"]).open("w", encoding="utf-8")
    log_file.write("Command: " + " ".join(cmd) + "\n\n")
    log_file.flush()
    process = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        env=os.environ.copy(),
    )
    log_file.close()
    waiter = threading.Thread(target=wait_for_process, args=(job_id, process), daemon=True)
    waiter.start()
    return job_snapshot(job_id)


def parse_multipart(handler: "AppHandler") -> Dict[str, Any]:
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ValueError("Expected multipart/form-data request.")
    form = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": handler.headers.get("Content-Length", "0"),
        },
    )
    fields: Dict[str, Any] = {}
    for key in form.keys():
        item = form[key]
        if isinstance(item, list):
            item = item[0]
        if item.filename:
            fields[key] = item
        else:
            fields[key] = item.value
    if "image" not in fields:
        raise ValueError("Missing image field.")
    return fields


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "ManimTeachWeb/0.1"

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        rel = unquote(parsed.path)
        if rel == "/":
            return str(WEB_ROOT / "index.html")
        if rel == "/preview/cinema":
            return str(WEB_ROOT / "cinema-preview.html")
        if rel.startswith("/static/"):
            return str(WEB_ROOT / rel.lstrip("/"))
        return str(WEB_ROOT / "index.html")

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), format % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            write_json_response(
                self,
                {
                    "ok": True,
                    "scriptExists": SCRIPT_PATH.exists(),
                    "root": str(ROOT),
                    "time": utc_timestamp(),
                },
            )
            return
        if path == "/api/jobs":
            with JOBS_LOCK:
                ids = list(JOBS.keys())
            write_json_response(self, {"jobs": [job_snapshot(job_id) for job_id in ids]})
            return
        match = re.fullmatch(r"/api/jobs/([^/]+)", path)
        if match:
            snapshot = job_snapshot(match.group(1))
            if not snapshot:
                write_json_response(self, {"error": "job not found"}, 404)
                return
            write_json_response(self, snapshot)
            return
        match = re.fullmatch(r"/api/jobs/([^/]+)/artifact/([^/]+)", path)
        if match:
            self.serve_artifact(match.group(1), unquote(match.group(2)))
            return
        match = re.fullmatch(r"/api/jobs/([^/]+)/image", path)
        if match:
            self.serve_job_file(match.group(1), "image")
            return
        match = re.fullmatch(r"/api/jobs/([^/]+)/video", path)
        if match:
            self.serve_job_file(match.group(1), "video")
            return
        if path.startswith("/api/"):
            write_json_response(self, {"error": "not found"}, 404)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/jobs":
            try:
                fields = parse_multipart(self)
                snapshot = start_generation_job(fields)
            except Exception as exc:
                write_json_response(self, {"error": str(exc)}, 400)
                return
            write_json_response(self, snapshot, 201)
            return
        if path == "/api/chat":
            self.handle_chat()
            return
        match = re.fullmatch(r"/api/jobs/([^/]+)/cancel", path)
        if match:
            self.cancel_job(match.group(1))
            return
        write_json_response(self, {"error": "not found"}, 404)

    def handle_chat(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            job_id = str(payload.get("jobId") or "")
            question = str(payload.get("message") or "").strip()
            current_time = float(payload.get("currentTime") or 0)
        except Exception as exc:
            write_json_response(self, {"error": f"invalid request: {exc}"}, 400)
            return
        if not question:
            write_json_response(self, {"error": "empty message"}, 400)
            return
        snapshot = job_snapshot(job_id)
        if not snapshot:
            write_json_response(self, {"error": "job not found"}, 404)
            return

        out_dir = Path(snapshot["outDir"])
        solution = ""
        if (out_dir / "solution.md").exists():
            solution = read_text(out_dir / "solution.md", limit=1400).strip()
        if snapshot["status"] == "done" and solution:
            answer = (
                f"已在 {current_time:.1f}s 暂停视频。当前问答接口已接通，后续可以把这里接入模型。"
                "\n\n我先根据已生成的解题稿给你定位：\n"
                + solution[:900]
            )
        elif snapshot["status"] == "running":
            answer = f"已收到问题并暂停在 {current_time:.1f}s。视频还在生成中，生成完成后这里可以结合讲稿和分镜回答。"
        else:
            answer = f"已收到问题并暂停在 {current_time:.1f}s。当前任务状态是 {snapshot['status']}，请先确认视频生成结果。"
        write_json_response(
            self,
            {
                "answer": answer,
                "jobId": job_id,
                "currentTime": current_time,
                "receivedAt": utc_timestamp(),
            },
        )

    def cancel_job(self, job_id: str) -> None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            pid = job.get("pid") if job else None
        if not job:
            write_json_response(self, {"error": "job not found"}, 404)
            return
        if pid:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        with JOBS_LOCK:
            job["status"] = "error"
            job["stage"] = "已取消"
            job["finished_at"] = utc_timestamp()
            job["return_code"] = -15
        write_json_response(self, job_snapshot(job_id))

    def serve_artifact(self, job_id: str, name: str) -> None:
        if not is_allowed_artifact(name):
            write_json_response(self, {"error": "artifact not allowed"}, 403)
            return
        snapshot = job_snapshot(job_id)
        if not snapshot:
            write_json_response(self, {"error": "job not found"}, 404)
            return
        path = Path(snapshot["outDir"]) / name
        if not path.exists() or not path.is_file():
            write_json_response(self, {"error": "artifact not found"}, 404)
            return
        content_type = "application/json" if path.suffix == ".json" else "text/plain"
        write_text_response(self, read_text(path), content_type=content_type)

    def serve_job_file(self, job_id: str, kind: str) -> None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if not job:
            write_json_response(self, {"error": "job not found"}, 404)
            return
        if kind == "image":
            file_path = Path(job["upload_path"])
        else:
            file_path = newest_mp4(Path(job["out_dir"])) or Path()
        if not file_path.exists() or not file_path.is_file():
            write_json_response(self, {"error": f"{kind} not found"}, 404)
            return
        if kind == "video":
            self.serve_range_file(file_path, "video/mp4")
            return
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.serve_range_file(file_path, content_type)

    def serve_range_file(self, path: Path, content_type: str) -> None:
        size = path.stat().st_size
        range_header = self.headers.get("Range")
        start, end = 0, size - 1
        status = HTTPStatus.OK
        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if match:
                if match.group(1):
                    start = int(match.group(1))
                if match.group(2):
                    end = int(match.group(2))
                end = min(end, size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
        if start > end or start >= size:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining > 0:
                chunk = source.read(min(1024 * 256, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the Manim Teach web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=7860, help="Bind port")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    if not SCRIPT_PATH.exists():
        print(f"Backend script not found: {SCRIPT_PATH}", file=sys.stderr)
        return 2
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Serving Manim Teach UI at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
