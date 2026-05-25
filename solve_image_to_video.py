#!/usr/bin/env python3
"""Generate a Chinese math-solution Manim video from an input image via model API.

The script intentionally uses only Python standard-library modules. It calls an
OpenAI-compatible model API, asks for structured JSON, writes the generated
solution artifacts, and renders the ManimCE scene in the local conda env.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_API_STYLE = "chat"
DEFAULT_JSON_MODE = "json_object"
DEFAULT_VISION_BASE_URL = "https://right.codes/codex/v1"
DEFAULT_VISION_MODEL = "gpt-5.5"
DEFAULT_VISION_API_KEY_ENV = "GPT55_API_KEY"
DEFAULT_VISION_API_STYLE = "chat"
DEFAULT_VISION_JSON_MODE = "json_object"
DEFAULT_CONDA_ENV = "manim-ce-018"
DEFAULT_CONDA_BIN = "/opt/conda/bin/conda"
DEFAULT_SCENE_CLASS = "SolutionVideo"


SOLUTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "problem_transcript",
        "solution_markdown",
        "lecture_script",
        "scenes_markdown",
        "render_notes",
    ],
    "properties": {
        "problem_transcript": {
            "type": "string",
            "description": "题目图片的文字转写；若有不确定处，明确标出。",
        },
        "solution_markdown": {
            "type": "string",
            "description": "中文 Markdown 解题步骤，包含关键公式和最终答案。",
        },
        "lecture_script": {
            "type": "string",
            "description": "中文视频讲稿，按镜头顺序书写，适合口播。",
        },
        "scenes_markdown": {
            "type": "string",
            "description": "Manim 分镜规划，包含每一幕的目的、视觉元素、动画和讲解要点。",
        },
        "render_notes": {
            "type": "string",
            "description": "题面识别不确定点、解题取舍、视频表达建议。",
        },
    },
}


CODE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scene_class", "manim_code", "render_notes"],
    "properties": {
        "scene_class": {
            "type": "string",
            "description": "ManimCE 场景类名，必须是合法 Python 标识符。",
        },
        "manim_code": {
            "type": "string",
            "description": "完整可运行的 ManimCE Python 源码，只使用 from manim import *。",
        },
        "render_notes": {
            "type": "string",
            "description": "渲染注意事项、实现设计说明、已知限制。",
        },
    },
}


REPAIR_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scene_class", "manim_code", "repair_summary"],
    "properties": {
        "scene_class": {
            "type": "string",
            "description": "修复后的 ManimCE 场景类名。",
        },
        "manim_code": {
            "type": "string",
            "description": "完整修复后的 ManimCE Python 源码。",
        },
        "repair_summary": {
            "type": "string",
            "description": "中文简述修复了什么问题。",
        },
    },
}


SKILL_DIGEST = """
你必须按已安装的 Manim 相关 skill 的约束工作：

manim-composer 要求：
- 先规划分镜，再写代码；要有清晰叙事钩子、逐步揭示、视觉连续性和关键 aha moment。
- scenes_markdown 必须说明每幕的 Duration、Purpose、Visual Elements、Content、Narration Notes、Technical Notes。
- 视频应先提出问题，再用代数和图形直观推进，最后收束到结论。

manimce-best-practices 要求：
- 使用 Manim Community Edition，不要使用 ManimGL；源码必须 `from manim import *`。
- 场景类继承 `Scene`、`MovingCameraScene` 或 `ThreeDScene`；默认用 `Scene`。
- 使用 `VGroup(...).arrange(...)`、`to_edge`、`next_to`、`align_to` 保证布局，不要让文字重叠。
- 中文必须用 `Text`/`MarkupText` 并指定 `font="Noto Sans CJK SC"`；不要把中文放进 `MathTex`。
- 数学公式使用 `MathTex`，并保持公式短小；复杂推导拆成多行，不要堆满画面。
- 代码必须兼容 ManimCE 0.18.x；不要依赖外部素材，除非使用同目录下的输入图片文件。
""".strip()


SOLUTION_SYSTEM_PROMPT = """
你是一名严谨的数学老师、中文视频讲稿作者和 Manim Community Edition 动画工程师。
你的任务是从题目图片中识别数学问题，给出准确解法，写出可讲授的中文讲稿，
并按 Manim 视频要求规划分镜。不要生成 Manim Python 源码，源码会由另一个模型生成。

输出必须是 JSON，字段必须符合调用方给出的 schema，不要输出 Markdown 代码围栏。
JSON 字符串中的换行和反斜杠必须合法转义；例如 LaTeX `\\sin` 在 JSON 字符串中要写成 `\\\\sin`。
""".strip()


CODE_SYSTEM_PROMPT = """
你是一名 Manim Community Edition 0.18.x 动画工程师。
你的任务是根据已经完成的题目转写、解题步骤、讲稿和分镜，生成高质量、可渲染的 ManimCE Python 源码。
不要重新解题，不要改变数学结论；只把给定内容实现成清晰、稳定、可渲染的视频。

输出必须是 JSON，字段必须符合调用方给出的 schema，不要输出 Markdown 代码围栏。
JSON 字符串中的换行和反斜杠必须合法转义；例如 LaTeX `\\sin` 在 JSON 字符串中要写成 `\\\\sin`。
""".strip()


SOLUTION_PROMPT_TEMPLATE = """
请根据题目信息完成一次端到端生成。

目标语言：{language}
目标 Manim 场景类名：{scene_class}
输入图片文件名：{image_filename}
输入方式：{input_mode_note}

{problem_text_block}

必须完成：
1. 识别或整理题目，写入 problem_transcript。若有看不清的符号，明确写出不确定点。
2. 给出严谨的中文解题步骤 solution_markdown。不要只给答案，要说明关键等价变形和理由。
3. 写出可口播的中文 lecture_script。讲稿要自然，有镜头节奏，不要像代码注释。
4. 按 skill 写出 scenes_markdown：逐幕规划、视觉元素、讲解点、技术实现注意事项。
5. 不要写 Manim Python 源码；代码会由 DeepSeek 在下一阶段生成。

分镜要为后续 Manim 实现做好准备：
- 每幕内容不要过满，要能在 16:9 视频中清楚展示。
- 中文屏幕文字用自然短句；数学公式单独列出。
- 明确哪些公式、图形、颜色编码、转场和强调动画要出现。
- 如果建议展示原题图，只能引用同目录的 `{image_filename}`。

{skill_digest}
""".strip()


CODE_PROMPT_TEMPLATE = """
请根据上一阶段已经完成的数学内容，生成完整可渲染的 ManimCE Python 源码。

目标语言：{language}
目标 Manim 场景类名：{scene_class}
输入图片文件名：{image_filename}

题目转写：
```markdown
{problem_transcript}
```

解题步骤：
```markdown
{solution_markdown}
```

视频讲稿：
```markdown
{lecture_script}
```

分镜规划：
```markdown
{scenes_markdown}
```

上一阶段备注：
```markdown
{solution_notes}
```

Manim 代码硬性要求：
- 必须 `from manim import *`，不得使用 `manimlib`。
- 必须定义类 `{scene_class}`；类名必须和 scene_class 字段一致。
- 画布 16:9，建议 1920x1080、30fps，深色背景。
- 中文文本使用 `Text(..., font="Noto Sans CJK SC")` 或封装 helper；数学公式才用 `MathTex`。
- 绝对不要把中文写进 `MathTex` 或 LaTeX 字符串。
- 每一屏内容要少而清晰。使用 `VGroup`、`arrange`、`to_edge`、`next_to` 控制布局，避免重叠。
- 对关键变量、等式、图形使用颜色编码，保持视觉连续性。
- 可以使用 `ImageMobject("{image_filename}")` 展示原题图片，但不是必须；如果使用，只能引用这个文件名。
- 不要依赖联网下载、外部字体文件、外部图片或音频。
- 不要使用过时或非 ManimCE 0.18 兼容 API。
- 源码中可以有简短英文注释，但屏幕文字和讲稿以中文为主。
- 不要生成旁白音频；只生成可视化动画视频。

{skill_digest}
""".strip()


REPAIR_PROMPT_TEMPLATE = """
上一次生成的 ManimCE 代码渲染失败。请只修复 Manim 代码，不要改变题目解法的数学含义。

目标场景类名：{scene_class}
输入图片文件名：{image_filename}

必须返回 JSON：
- scene_class：修复后的类名，优先保持 `{scene_class}`
- manim_code：完整 Python 文件
- repair_summary：中文简述修复点

常见修复方向：
- 中文不能放进 MathTex；必须改为 Text(font="Noto Sans CJK SC")。
- MathTex 只保留数学符号，必要时拆成多段。
- 检查括号、缩进、类名、变量名、不存在的 API。
- 检查 VGroup/arrange/next_to 布局，避免过宽文本出框。
- 保持 `from manim import *`，兼容 ManimCE 0.18.x。

题目转写：
{problem_transcript}

解题稿：
{solution_markdown}

分镜：
{scenes_markdown}

当前代码：
```python
{current_code}
```

Manim 渲染日志末尾：
```text
{render_log}
```
""".strip()


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines into os.environ without overriding exports."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def safe_slug(value: str, fallback: str = "run") -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return slug or fallback


def sanitize_scene_class(name: str) -> str:
    candidate = re.sub(r"\W+", "_", name.strip())
    if not candidate:
        candidate = DEFAULT_SCENE_CLASS
    if candidate[0].isdigit():
        candidate = "_" + candidate
    return candidate


def default_out_dir(image_path: Path) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    stem = safe_slug(image_path.stem, "image")
    return Path("runs") / f"{stem}_{stamp}"


def guess_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed and guessed.startswith("image/"):
        return guessed
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def encode_image_data_url(path: Path) -> str:
    mime = guess_mime(path)
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    fence_match = re.fullmatch(r"```(?:python|py)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return cleaned


class ModelOutputParseError(RuntimeError):
    def __init__(self, message: str, output_text: str, response: Dict[str, Any]):
        super().__init__(message)
        self.output_text = output_text
        self.response = response


def escape_invalid_json_backslashes(text: str) -> str:
    """Repair common model JSON mistakes inside strings.

    Some OpenAI-compatible gateways do not enforce JSON schema strictly. Model
    output that contains Manim/LaTeX often includes raw `\sin` or actual newlines
    inside JSON strings. This pass preserves valid JSON escapes and escapes the
    invalid ones so json.loads can recover the object.
    """
    out: List[str] = []
    in_string = False
    i = 0
    valid_simple_escapes = {'"', "\\", "/", "b", "f", "n", "r", "t"}

    while i < len(text):
        ch = text[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if ch == '"':
            out.append(ch)
            in_string = False
            i += 1
            continue

        if ch == "\n":
            out.append("\\n")
            i += 1
            continue
        if ch == "\r":
            out.append("\\r")
            i += 1
            continue
        if ch == "\t":
            out.append("\\t")
            i += 1
            continue

        if ch == "\\":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if nxt in valid_simple_escapes:
                out.append("\\")
                out.append(nxt)
                i += 2
                continue
            if nxt == "u" and i + 5 < len(text):
                hex_part = text[i + 2 : i + 6]
                if re.fullmatch(r"[0-9A-Fa-f]{4}", hex_part):
                    out.append("\\u")
                    out.append(hex_part)
                    i += 6
                    continue
            out.append("\\\\")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def parse_json_text(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = escape_invalid_json_backslashes(cleaned)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            clipped = cleaned[start : end + 1]
            try:
                return json.loads(clipped)
            except json.JSONDecodeError:
                return json.loads(escape_invalid_json_backslashes(clipped))
        raise


def extract_response_text(response: Dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "\n".join(parts)

    parts = []
    for output_item in response.get("output", []) or []:
        for content in output_item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            if isinstance(content.get("text"), str):
                parts.append(content["text"])
            elif isinstance(content.get("content"), str):
                parts.append(content["content"])
    if parts:
        return "\n".join(parts)

    raise ValueError("API response did not contain text output.")


def api_endpoint(base_url: str, api_style: str, explicit_api_url: Optional[str]) -> str:
    if explicit_api_url:
        return explicit_api_url
    root = base_url.rstrip("/")
    if api_style == "responses":
        return f"{root}/responses"
    if api_style == "chat":
        return f"{root}/chat/completions"
    raise ValueError(f"Unsupported api_style: {api_style}")


def json_mode_payload(json_mode: str, schema_name: str, schema: Dict[str, Any], api_style: str) -> Dict[str, Any]:
    if json_mode == "none":
        return {}
    if api_style == "responses":
        if json_mode == "schema":
            return {
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    }
                }
            }
        return {"text": {"format": {"type": "json_object"}}}

    if json_mode == "schema":
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }
        }
    return {"response_format": {"type": "json_object"}}


def build_solution_prompt(
    language: str,
    scene_class: str,
    image_filename: str,
    problem_text: Optional[str],
    send_image: bool,
) -> str:
    if send_image:
        input_mode_note = "通过 API 图片输入识别题目。"
        if problem_text:
            problem_text_block = (
                "旁路题面文本（仅作参考，必须以图片识别为准；如图片与文本不一致，请在 problem_transcript 中说明）：\n"
                "```text\n" + problem_text.strip() + "\n```"
            )
        else:
            problem_text_block = "题面文本：未提供，请直接识别随消息附带的题目图片。"
    elif problem_text:
        input_mode_note = "使用题面文本；图片只作为 Manim 画面素材引用，不通过 API 识别。"
        problem_text_block = "题面文本：\n```text\n" + problem_text.strip() + "\n```"
    else:
        input_mode_note = "文本模型模式，但尚未提供题面文本。"
        problem_text_block = "题面文本：未提供。"
    return SOLUTION_PROMPT_TEMPLATE.format(
        language=language,
        scene_class=scene_class,
        image_filename=image_filename,
        input_mode_note=input_mode_note,
        problem_text_block=problem_text_block,
        skill_digest=SKILL_DIGEST,
    )


def build_chat_payload(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_data_url: Optional[str],
    max_tokens: int,
    temperature: float,
    json_mode: str,
    schema_name: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    if image_data_url:
        user_content: Any = [{"type": "text", "text": user_prompt}]
        user_content.append({"type": "image_url", "image_url": {"url": image_data_url}})
    else:
        user_content = user_prompt
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    payload.update(json_mode_payload(json_mode, schema_name, schema, "chat"))
    return payload


def build_responses_payload(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_data_url: Optional[str],
    max_tokens: int,
    temperature: float,
    json_mode: str,
    schema_name: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
    if image_data_url:
        user_content.append({"type": "input_image", "image_url": image_data_url})
    payload: Dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    payload.update(json_mode_payload(json_mode, schema_name, schema, "responses"))
    return payload


def build_payload(
    api_style: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_data_url: Optional[str],
    max_tokens: int,
    temperature: float,
    json_mode: str,
    schema_name: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    if api_style == "responses":
        return build_responses_payload(
            model,
            system_prompt,
            user_prompt,
            image_data_url,
            max_tokens,
            temperature,
            json_mode,
            schema_name,
            schema,
        )
    return build_chat_payload(
        model,
        system_prompt,
        user_prompt,
        image_data_url,
        max_tokens,
        temperature,
        json_mode,
        schema_name,
        schema,
    )


def post_json(url: str, api_key: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {exc.code}: {error_body[:4000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"API request failed: {exc}") from exc

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API returned non-JSON response: {response_body[:2000]}") from exc


def resolve_api_key(env_name: str) -> str:
    api_key = os.environ.get(env_name)
    fallback_envs = ["MODEL_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GPT55_API_KEY", "VISION_API_KEY"]
    for fallback_env in fallback_envs:
        if api_key:
            break
        if fallback_env != env_name:
            api_key = os.environ.get(fallback_env)
    if not api_key:
        fallback_hint = ", ".join([env_name] + [name for name in fallback_envs if name != env_name])
        raise RuntimeError(
            f"Missing API key. Set one of these environment variables before running: {fallback_hint}."
        )
    return api_key


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_solution_and_code(solution: Dict[str, Any], code_result: Dict[str, Any], scene_class: str) -> Dict[str, Any]:
    return {
        "problem_transcript": str(solution.get("problem_transcript", "")).strip(),
        "solution_markdown": str(solution.get("solution_markdown", "")).strip(),
        "lecture_script": str(solution.get("lecture_script", "")).strip(),
        "scenes_markdown": str(solution.get("scenes_markdown", "")).strip(),
        "scene_class": sanitize_scene_class(str(code_result.get("scene_class") or scene_class)),
        "manim_code": strip_code_fences(str(code_result.get("manim_code") or "")),
        "render_notes": (
            "解题/分镜备注：\n"
            + str(solution.get("render_notes", "")).strip()
            + "\n\n代码/渲染备注：\n"
            + str(code_result.get("render_notes", "")).strip()
        ).strip(),
    }


def write_generation_artifacts(out_dir: Path, generation: Dict[str, Any]) -> Tuple[Path, str]:
    scene_class = sanitize_scene_class(str(generation.get("scene_class") or DEFAULT_SCENE_CLASS))
    code = strip_code_fences(str(generation.get("manim_code") or ""))
    if not code:
        raise ValueError("Model response did not include manim_code.")

    write_text(out_dir / "problem_transcript.md", str(generation.get("problem_transcript", "")).strip() + "\n")
    write_text(out_dir / "solution.md", str(generation.get("solution_markdown", "")).strip() + "\n")
    write_text(out_dir / "lecture_script.md", str(generation.get("lecture_script", "")).strip() + "\n")
    write_text(out_dir / "scenes.md", str(generation.get("scenes_markdown", "")).strip() + "\n")
    write_text(out_dir / "render_notes.md", str(generation.get("render_notes", "")).strip() + "\n")
    write_json(out_dir / "generation.json", generation)
    code_path = out_dir / "video_scene.py"
    write_text(code_path, code.rstrip() + "\n")
    return code_path, scene_class


def find_scene_classes(code: str) -> List[str]:
    pattern = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(?:Scene|MovingCameraScene|ThreeDScene)\s*\)\s*:", re.M)
    return pattern.findall(code)


def validate_code(code_path: Path, scene_class: str) -> List[str]:
    code = code_path.read_text(encoding="utf-8", errors="replace")
    warnings = []
    if "from manim import *" not in code:
        warnings.append("源码中未找到 `from manim import *`。")
    if "manimlib" in code:
        warnings.append("源码中出现 `manimlib`，这属于 ManimGL 而非 ManimCE。")
    classes = find_scene_classes(code)
    if scene_class not in classes:
        if classes:
            warnings.append(f"未找到类 `{scene_class}`，但找到了 {classes}；将尝试渲染第一个类 `{classes[0]}`。")
        else:
            warnings.append(f"未找到可渲染的 Scene 类 `{scene_class}`。")
    if "MathTex" in code and re.search(r"MathTex\([^)]*[\u4e00-\u9fff]", code, flags=re.DOTALL):
        warnings.append("检测到 MathTex 内可能包含中文，渲染可能失败。")
    return warnings


def choose_render_scene(code_path: Path, requested_scene: str) -> str:
    code = code_path.read_text(encoding="utf-8", errors="replace")
    classes = find_scene_classes(code)
    if requested_scene in classes:
        return requested_scene
    if classes:
        return classes[0]
    return requested_scene


def quality_flag(quality: str) -> str:
    aliases = {
        "l": "-ql",
        "low": "-ql",
        "m": "-qm",
        "medium": "-qm",
        "h": "-qh",
        "high": "-qh",
        "k": "-qk",
        "4k": "-qk",
    }
    if quality.startswith("-q"):
        return quality
    return aliases.get(quality.lower(), "-qh")


def render_manim(
    out_dir: Path,
    code_path: Path,
    scene_class: str,
    conda_bin: str,
    conda_env: str,
    quality: str,
    timeout: int,
    log_name: str,
) -> Tuple[bool, Path, str]:
    conda_exe = conda_bin
    if not Path(conda_exe).exists():
        conda_exe = "conda"
    cmd = [
        conda_exe,
        "run",
        "-n",
        conda_env,
        "manim",
        quality_flag(quality),
        code_path.name,
        scene_class,
    ]
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(out_dir),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        output = proc.stdout or ""
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        output += f"\n\n[timeout] Render exceeded {timeout} seconds."
        ok = False

    elapsed = time.time() - started
    log_path = out_dir / log_name
    write_text(
        log_path,
        "Command: " + " ".join(cmd) + "\n"
        + f"Elapsed: {elapsed:.1f}s\n"
        + f"Success: {ok}\n\n"
        + output,
    )
    return ok, log_path, output


def newest_mp4(out_dir: Path) -> Optional[Path]:
    media_dir = out_dir / "media" / "videos"
    if not media_dir.exists():
        return None
    candidates = list(media_dir.rglob("*.mp4"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def truncated_tail(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def call_model_for_solution(args: argparse.Namespace, image_data_url: Optional[str], image_filename: str, scene_class: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prompt = build_solution_prompt(args.language, scene_class, image_filename, args.problem_text_content, bool(image_data_url))
    payload = build_payload(
        args.vision_api_style,
        args.vision_model,
        SOLUTION_SYSTEM_PROMPT,
        prompt,
        image_data_url,
        args.vision_max_tokens,
        args.vision_temperature,
        args.vision_json_mode,
        "math_solution_generation",
        SOLUTION_SCHEMA,
    )
    response = post_json(
        api_endpoint(args.vision_base_url, args.vision_api_style, args.vision_api_url),
        resolve_api_key(args.vision_api_key_env),
        payload,
        args.api_timeout,
    )
    text = extract_response_text(response)
    try:
        solution = parse_json_text(text)
    except Exception as exc:
        raise ModelOutputParseError(str(exc), text, response) from exc
    return solution, response


def call_model_for_code(args: argparse.Namespace, image_filename: str, scene_class: str, solution: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prompt = CODE_PROMPT_TEMPLATE.format(
        language=args.language,
        scene_class=scene_class,
        image_filename=image_filename,
        problem_transcript=str(solution.get("problem_transcript", "")),
        solution_markdown=str(solution.get("solution_markdown", "")),
        lecture_script=str(solution.get("lecture_script", "")),
        scenes_markdown=str(solution.get("scenes_markdown", "")),
        solution_notes=str(solution.get("render_notes", "")),
        skill_digest=SKILL_DIGEST,
    )
    payload = build_payload(
        args.api_style,
        args.model,
        CODE_SYSTEM_PROMPT,
        prompt,
        None,
        args.max_tokens,
        args.temperature,
        args.json_mode,
        "manim_code_generation",
        CODE_SCHEMA,
    )
    response = post_json(
        api_endpoint(args.base_url, args.api_style, args.api_url),
        resolve_api_key(args.api_key_env),
        payload,
        args.api_timeout,
    )
    text = extract_response_text(response)
    try:
        code_result = parse_json_text(text)
    except Exception as exc:
        raise ModelOutputParseError(str(exc), text, response) from exc
    return code_result, response


def call_model_for_repair(
    args: argparse.Namespace,
    image_filename: str,
    scene_class: str,
    generation: Dict[str, Any],
    current_code: str,
    render_log: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prompt = REPAIR_PROMPT_TEMPLATE.format(
        scene_class=scene_class,
        image_filename=image_filename,
        problem_transcript=str(generation.get("problem_transcript", "")),
        solution_markdown=str(generation.get("solution_markdown", "")),
        scenes_markdown=str(generation.get("scenes_markdown", "")),
        current_code=current_code,
        render_log=truncated_tail(render_log),
    )
    payload = build_payload(
        args.api_style,
        args.model,
        CODE_SYSTEM_PROMPT,
        prompt,
        None,
        args.repair_max_tokens,
        args.temperature,
        args.json_mode,
        "manim_code_repair",
        REPAIR_SCHEMA,
    )
    response = post_json(
        api_endpoint(args.base_url, args.api_style, args.api_url),
        resolve_api_key(args.api_key_env),
        payload,
        args.api_timeout,
    )
    text = extract_response_text(response)
    try:
        repair = parse_json_text(text)
    except Exception as exc:
        raise ModelOutputParseError(str(exc), text, response) from exc
    return repair, response


def copy_input_image(image_path: Path, out_dir: Path) -> str:
    suffix = image_path.suffix.lower() or ".png"
    image_filename = f"input{suffix}"
    shutil.copy2(str(image_path), str(out_dir / image_filename))
    return image_filename


def load_problem_text(image_path: Path, problem_text: Optional[str], problem_text_file: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if problem_text:
        return problem_text.strip(), "inline"
    if problem_text_file:
        path = Path(problem_text_file).expanduser().resolve()
        return path.read_text(encoding="utf-8", errors="replace").strip(), str(path)

    candidates = [
        image_path.with_suffix(".txt"),
        image_path.with_suffix(".md"),
        image_path.parent / f"{image_path.stem}.ocr.txt",
        image_path.parent / f"{image_path.stem}.ocr.md",
        image_path.parent / "problem.txt",
        image_path.parent / "problem.md",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="replace").strip(), str(candidate)
    return None, None


def text_only_endpoint(base_url: str, api_style: str) -> bool:
    return api_style == "chat" and "api.deepseek.com" in base_url.lower()


def should_send_image(args: argparse.Namespace, problem_text: Optional[str]) -> bool:
    if args.input_mode == "image":
        return True
    if args.input_mode == "text":
        return False
    if problem_text and not args.prefer_vision_over_text:
        return False
    if text_only_endpoint(args.vision_base_url, args.vision_api_style):
        return False
    return True


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call a model API to solve a math image and render a ManimCE explanation video.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("image", help="题目图片路径，例如 6667b52c46f1a5654f104b0e721c4514.png")
    parser.add_argument("--out-dir", help="输出目录；默认写入 runs/<图片名>_<时间戳>")
    parser.add_argument("--model", default=os.environ.get("CODE_MODEL_NAME", os.environ.get("MODEL_NAME", DEFAULT_MODEL)), help="代码模型名称，默认 DeepSeek")
    parser.add_argument("--base-url", default=os.environ.get("CODE_MODEL_API_BASE_URL", os.environ.get("MODEL_API_BASE_URL", DEFAULT_BASE_URL)), help="代码模型 API base URL")
    parser.add_argument("--api-url", default=os.environ.get("CODE_MODEL_API_URL"), help="代码模型完整 API URL；设置后覆盖 --base-url 和 --api-style 组合")
    parser.add_argument("--api-style", choices=["chat", "responses"], default=os.environ.get("CODE_MODEL_API_STYLE", os.environ.get("MODEL_API_STYLE", DEFAULT_API_STYLE)), help="代码模型 API 风格")
    parser.add_argument("--api-key-env", default=os.environ.get("CODE_MODEL_API_KEY_ENV", os.environ.get("MODEL_API_KEY_ENV", DEFAULT_API_KEY_ENV)), help="读取代码模型 API key 的环境变量名")
    parser.add_argument("--json-mode", choices=["schema", "json_object", "none"], default=os.environ.get("CODE_MODEL_JSON_MODE", os.environ.get("MODEL_JSON_MODE", DEFAULT_JSON_MODE)), help="代码模型结构化输出模式")
    parser.add_argument("--vision-model", default=os.environ.get("VISION_MODEL_NAME", DEFAULT_VISION_MODEL), help="读图/解题模型名称")
    parser.add_argument("--vision-base-url", default=os.environ.get("VISION_MODEL_API_BASE_URL", DEFAULT_VISION_BASE_URL), help="读图/解题模型 API base URL")
    parser.add_argument("--vision-api-url", default=os.environ.get("VISION_MODEL_API_URL"), help="读图/解题模型完整 API URL；设置后覆盖 --vision-base-url")
    parser.add_argument("--vision-api-style", choices=["chat", "responses"], default=os.environ.get("VISION_MODEL_API_STYLE", DEFAULT_VISION_API_STYLE), help="读图/解题模型 API 风格")
    parser.add_argument("--vision-api-key-env", default=os.environ.get("VISION_MODEL_API_KEY_ENV", DEFAULT_VISION_API_KEY_ENV), help="读取读图/解题模型 API key 的环境变量名")
    parser.add_argument("--vision-json-mode", choices=["schema", "json_object", "none"], default=os.environ.get("VISION_MODEL_JSON_MODE", DEFAULT_VISION_JSON_MODE), help="读图/解题模型结构化输出模式")
    parser.add_argument("--input-mode", choices=["auto", "image", "text"], default=os.environ.get("VISION_INPUT_MODE", os.environ.get("MODEL_INPUT_MODE", "auto")), help="读图输入模式；auto 优先用支持图片的 GPT-5.5")
    parser.add_argument("--prefer-vision-over-text", action="store_true", default=os.environ.get("PREFER_VISION_OVER_TEXT", "1") not in {"0", "false", "False"}, help="即使存在 sidecar 文本，也优先让视觉模型读图")
    parser.add_argument("--problem-text", help="直接传入题面文本；设置 --input-mode text 时使用")
    parser.add_argument("--problem-text-file", help="题面文本文件路径；设置 --input-mode text 时使用")
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("CODE_MODEL_MAX_TOKENS", "12000")), help="代码生成最大输出 token")
    parser.add_argument("--vision-max-tokens", type=int, default=int(os.environ.get("VISION_MODEL_MAX_TOKENS", "9000")), help="读图/解题最大输出 token")
    parser.add_argument("--repair-max-tokens", type=int, default=int(os.environ.get("CODE_MODEL_REPAIR_MAX_TOKENS", "9000")), help="修复轮最大输出 token")
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("CODE_MODEL_TEMPERATURE", "0.2")), help="代码模型采样温度")
    parser.add_argument("--vision-temperature", type=float, default=float(os.environ.get("VISION_MODEL_TEMPERATURE", "0.2")), help="读图/解题模型采样温度")
    parser.add_argument("--api-timeout", type=int, default=300, help="API 请求超时秒数")
    parser.add_argument("--scene-class", default=DEFAULT_SCENE_CLASS, help="希望模型生成的 Manim 场景类名")
    parser.add_argument("--language", default="中文，简体中文讲解", help="解题、讲稿和屏幕文字语言")
    parser.add_argument("--conda-bin", default=DEFAULT_CONDA_BIN, help="conda 可执行文件路径")
    parser.add_argument("--conda-env", default=DEFAULT_CONDA_ENV, help="用于渲染的 conda 环境名")
    parser.add_argument("--quality", default="h", help="Manim 渲染质量：l/m/h/k 或 -ql/-qm/-qh/-qk")
    parser.add_argument("--render-timeout", type=int, default=600, help="单次 Manim 渲染超时秒数")
    parser.add_argument("--max-repair-attempts", type=int, default=2, help="渲染失败后 API 修复重试次数")
    parser.add_argument("--no-render", action="store_true", help="只生成文件，不渲染视频")
    parser.add_argument("--dry-run", action="store_true", help="只创建输出目录和提示词，不调用 API、不渲染")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    load_env_file(Path(__file__).resolve().with_name(".env"))
    load_env_file(Path.cwd() / ".env")
    args = build_arg_parser().parse_args(argv)
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists():
        eprint(f"Image not found: {image_path}")
        return 2
    if not image_path.is_file():
        eprint(f"Image path is not a file: {image_path}")
        return 2

    try:
        problem_text, problem_text_source = load_problem_text(image_path, args.problem_text, args.problem_text_file)
    except Exception as exc:
        eprint(f"Failed to read problem text: {exc}")
        return 2
    args.problem_text_content = problem_text

    scene_class = sanitize_scene_class(args.scene_class)
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else default_out_dir(image_path).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    image_filename = copy_input_image(image_path, out_dir)
    send_image = should_send_image(args, problem_text)
    solution_prompt = build_solution_prompt(args.language, scene_class, image_filename, problem_text, send_image)

    write_text(out_dir / "prompt.md", solution_prompt + "\n")
    write_text(out_dir / "solution_prompt.md", solution_prompt + "\n")
    write_json(
        out_dir / "run_config.json",
        {
            "image": str(image_path),
            "copied_image": image_filename,
            "vision_model": args.vision_model,
            "vision_base_url": args.vision_base_url,
            "vision_api_url": args.vision_api_url,
            "vision_api_style": args.vision_api_style,
            "vision_api_key_env": args.vision_api_key_env,
            "vision_json_mode": args.vision_json_mode,
            "code_model": args.model,
            "code_base_url": args.base_url,
            "code_api_url": args.api_url,
            "code_api_style": args.api_style,
            "code_api_key_env": args.api_key_env,
            "code_json_mode": args.json_mode,
            "input_mode": args.input_mode,
            "send_image": send_image,
            "prefer_vision_over_text": args.prefer_vision_over_text,
            "problem_text_source": problem_text_source,
            "scene_class": scene_class,
            "conda_env": args.conda_env,
            "quality": args.quality,
            "dry_run": args.dry_run,
            "no_render": args.no_render,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        },
    )

    eprint(f"[1/4] Output dir: {out_dir}")
    eprint(f"[1/4] Copied image: {out_dir / image_filename}")
    if problem_text_source:
        eprint(f"[1/4] Problem text source: {problem_text_source}")
    elif text_only_endpoint(args.vision_base_url, args.vision_api_style) and not send_image:
        eprint("The selected vision/solution endpoint does not accept image_url messages.")
        eprint("Provide --problem-text, --problem-text-file, or an image sidecar .txt/.md file.")
        if not args.dry_run:
            return 2
    if args.dry_run:
        preview_solution = {
            "problem_transcript": "<由读图/解题模型生成>",
            "solution_markdown": "<由读图/解题模型生成>",
            "lecture_script": "<由读图/解题模型生成>",
            "scenes_markdown": "<由读图/解题模型生成>",
            "render_notes": "<由读图/解题模型生成>",
        }
        code_prompt_preview = CODE_PROMPT_TEMPLATE.format(
            language=args.language,
            scene_class=scene_class,
            image_filename=image_filename,
            problem_transcript=preview_solution["problem_transcript"],
            solution_markdown=preview_solution["solution_markdown"],
            lecture_script=preview_solution["lecture_script"],
            scenes_markdown=preview_solution["scenes_markdown"],
            solution_notes=preview_solution["render_notes"],
            skill_digest=SKILL_DIGEST,
        )
        write_text(out_dir / "code_prompt_preview.md", code_prompt_preview + "\n")
        eprint("[dry-run] Wrote prompts and run_config.json; API calls skipped.")
        return 0

    image_data_url = encode_image_data_url(out_dir / image_filename) if send_image else None
    eprint(f"[2/4] Calling vision/solution API ({args.vision_api_style}) with model: {args.vision_model}")
    try:
        solution, solution_raw_response = call_model_for_solution(args, image_data_url, image_filename, scene_class)
    except ModelOutputParseError as exc:
        write_json(out_dir / "solution_model_response.json", exc.response)
        write_text(out_dir / "solution_raw_model_output.txt", exc.output_text)
        write_text(out_dir / "solution_api_error.txt", str(exc) + "\n")
        eprint(f"Vision/solution API returned unparsable JSON. See {out_dir / 'solution_raw_model_output.txt'}")
        eprint(str(exc))
        return 1
    except Exception as exc:
        write_text(out_dir / "solution_api_error.txt", str(exc) + "\n")
        eprint(f"Vision/solution API failed. See {out_dir / 'solution_api_error.txt'}")
        eprint(str(exc))
        return 1

    write_json(out_dir / "solution_model_response.json", solution_raw_response)
    write_json(out_dir / "solution_generation.json", solution)
    write_text(out_dir / "problem_transcript.md", str(solution.get("problem_transcript", "")).strip() + "\n")
    write_text(out_dir / "solution.md", str(solution.get("solution_markdown", "")).strip() + "\n")
    write_text(out_dir / "lecture_script.md", str(solution.get("lecture_script", "")).strip() + "\n")
    write_text(out_dir / "scenes.md", str(solution.get("scenes_markdown", "")).strip() + "\n")

    code_prompt = CODE_PROMPT_TEMPLATE.format(
        language=args.language,
        scene_class=scene_class,
        image_filename=image_filename,
        problem_transcript=str(solution.get("problem_transcript", "")),
        solution_markdown=str(solution.get("solution_markdown", "")),
        lecture_script=str(solution.get("lecture_script", "")),
        scenes_markdown=str(solution.get("scenes_markdown", "")),
        solution_notes=str(solution.get("render_notes", "")),
        skill_digest=SKILL_DIGEST,
    )
    write_text(out_dir / "code_prompt.md", code_prompt + "\n")

    eprint(f"[3/4] Calling code API ({args.api_style}) with model: {args.model}")
    try:
        code_result, code_raw_response = call_model_for_code(args, image_filename, scene_class, solution)
    except ModelOutputParseError as exc:
        write_json(out_dir / "code_model_response.json", exc.response)
        write_text(out_dir / "code_raw_model_output.txt", exc.output_text)
        write_text(out_dir / "code_api_error.txt", str(exc) + "\n")
        eprint(f"Code API returned unparsable JSON. See {out_dir / 'code_raw_model_output.txt'}")
        eprint(str(exc))
        return 1
    except Exception as exc:
        write_text(out_dir / "code_api_error.txt", str(exc) + "\n")
        eprint(f"Code API failed. See {out_dir / 'code_api_error.txt'}")
        eprint(str(exc))
        return 1

    write_json(out_dir / "code_model_response.json", code_raw_response)
    write_json(out_dir / "code_generation.json", code_result)
    generation = merge_solution_and_code(solution, code_result, scene_class)
    write_json(out_dir / "model_response.json", {"solution_model": solution_raw_response, "code_model": code_raw_response})
    code_path, generated_scene_class = write_generation_artifacts(out_dir, generation)
    render_scene = choose_render_scene(code_path, generated_scene_class)
    warnings = validate_code(code_path, render_scene)
    if warnings:
        write_text(out_dir / "validation_warnings.txt", "\n".join(warnings) + "\n")
        for warning in warnings:
            eprint(f"[warning] {warning}")

    eprint(f"[3/4] Wrote artifacts: {code_path}")
    if args.no_render:
        eprint("[no-render] Generation complete; render skipped.")
        return 0

    eprint(f"[4/4] Rendering Manim scene: {render_scene}")
    ok, log_path, render_log = render_manim(
        out_dir,
        code_path,
        render_scene,
        args.conda_bin,
        args.conda_env,
        args.quality,
        args.render_timeout,
        "render.log",
    )

    attempt = 0
    while not ok and attempt < args.max_repair_attempts:
        attempt += 1
        eprint(f"[repair {attempt}/{args.max_repair_attempts}] Render failed; calling model for code repair.")
        try:
            repair, repair_response = call_model_for_repair(
                args,
                image_filename,
                render_scene,
                generation,
                code_path.read_text(encoding="utf-8", errors="replace"),
                render_log,
            )
        except ModelOutputParseError as exc:
            write_json(out_dir / f"repair_{attempt}_response.json", exc.response)
            write_text(out_dir / f"repair_{attempt}_raw_output.txt", exc.output_text)
            write_text(out_dir / f"repair_{attempt}_api_error.txt", str(exc) + "\n")
            eprint(f"Repair API returned unparsable JSON. See {out_dir / f'repair_{attempt}_raw_output.txt'}")
            break
        except Exception as exc:
            write_text(out_dir / f"repair_{attempt}_api_error.txt", str(exc) + "\n")
            eprint(f"Repair API call failed. See {out_dir / f'repair_{attempt}_api_error.txt'}")
            break

        write_json(out_dir / f"repair_{attempt}_response.json", repair_response)
        repair_code = strip_code_fences(str(repair.get("manim_code", "")))
        if not repair_code:
            write_json(out_dir / f"repair_{attempt}_invalid.json", repair)
            eprint(f"[repair {attempt}] Model did not return manim_code.")
            break
        render_scene = sanitize_scene_class(str(repair.get("scene_class") or render_scene))
        write_text(code_path, repair_code.rstrip() + "\n")
        write_text(out_dir / f"repair_{attempt}_summary.md", str(repair.get("repair_summary", "")).strip() + "\n")
        render_scene = choose_render_scene(code_path, render_scene)
        ok, log_path, render_log = render_manim(
            out_dir,
            code_path,
            render_scene,
            args.conda_bin,
            args.conda_env,
            args.quality,
            args.render_timeout,
            f"render_repair_{attempt}.log",
        )

    if not ok:
        eprint(f"Render failed. Last log: {log_path}")
        return 1

    video_path = newest_mp4(out_dir)
    if video_path:
        write_text(out_dir / "video_path.txt", str(video_path) + "\n")
        eprint(f"Render complete: {video_path}")
    else:
        eprint("Render completed, but no mp4 was found under media/videos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
