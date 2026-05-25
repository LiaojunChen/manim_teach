# 图片题目生成 Manim 解题视频

脚本：`solve_image_to_video.py`

这个脚本会执行完整流程：

1. 复制输入题目图片到输出目录。
2. 调用 GPT-5.5 读图，生成题目转写、中文解题步骤、讲稿和分镜。
3. 调用 DeepSeek 根据解题稿和分镜生成 ManimCE 源码。
4. 写出 `solution.md`、`lecture_script.md`、`scenes.md`、`video_scene.py` 等文件。
5. 使用 conda 环境 `manim-ce-018` 渲染视频。
6. 如果 Manim 渲染失败，会把渲染日志发回 DeepSeek，自动修复代码并重试。

## 默认两模型调用

当前默认配置：

- 读图/解题模型：`gpt-5.5`
- 读图/解题接口：`https://right.codes/codex/v1`
- 读图/解题 key 环境变量：`GPT55_API_KEY`
- 代码模型：`deepseek-v4-pro`
- 代码接口：`https://api.deepseek.com`
- 代码 key 环境变量：`DEEPSEEK_API_KEY`
- 结构化输出：`json_object`

脚本会自动读取同目录 `.env`。DeepSeek 当前 `/chat/completions` 接口只接受文本消息，不接受 OpenAI 风格的 `image_url` 图片消息，所以脚本不会让 DeepSeek 读图，而是让 GPT-5.5 读图并生成解题文本，再把文本交给 DeepSeek 写程序。

如果图片旁边存在同名 `.txt` 或 `.md`，默认只作为 GPT-5.5 读图时的参考文本；仍以图片识别为准。若想完全不读图、只使用文本，可加 `--input-mode text`。

当前接口探测结果：

- DeepSeek `json_object` 文本调用正常。
- `right.codes` 的 `/models` 能列出 `gpt-5.5`。
- 但 `right.codes` 对 `gpt-5.5` 的轻量 `/chat/completions` 和 `/responses` 调用当前返回 `403 openai_error`。如果正式运行在第一阶段失败，先检查该网关的模型权限、额度或上游状态。

在 `manim_teach` 目录内可这样运行：

```bash
python3 solve_image_to_video.py ../6667b52c46f1a5654f104b0e721c4514.png \
  --out-dir ../runs/trig_gpt55_deepseek_video \
  --quality h
```

生成完成后，主要产物在：

- `../runs/trig_gpt55_deepseek_video/problem_transcript.md`
- `../runs/trig_gpt55_deepseek_video/solution.md`
- `../runs/trig_gpt55_deepseek_video/lecture_script.md`
- `../runs/trig_gpt55_deepseek_video/scenes.md`
- `../runs/trig_gpt55_deepseek_video/video_scene.py`
- `../runs/trig_gpt55_deepseek_video/solution_model_response.json`
- `../runs/trig_gpt55_deepseek_video/code_model_response.json`
- `../runs/trig_gpt55_deepseek_video/video_path.txt`
- `../runs/trig_gpt55_deepseek_video/media/videos/.../*.mp4`

## 只生成文件，不渲染

```bash
python3 solve_image_to_video.py 题目.png \
  --out-dir runs/case_no_render \
  --no-render
```

## 强制只用文本，不读图

```bash
python3 solve_image_to_video.py 题目.png \
  --input-mode text \
  --problem-text-file 题目.txt \
  --out-dir runs/text_only_case
```

## 只检查提示词，不调用 API

```bash
python3 solve_image_to_video.py 题目.png \
  --out-dir runs/case_dry_run \
  --dry-run
```

## 覆盖模型

替换读图模型：

```bash
python3 solve_image_to_video.py 题目.png \
  --vision-base-url https://your-vision-api.example/v1 \
  --vision-api-key-env VISION_API_KEY \
  --vision-model your-vision-model \
  --out-dir runs/custom_vision_case
```

替换代码模型：

```bash
python3 solve_image_to_video.py 题目.png \
  --base-url https://your-code-api.example/v1 \
  --api-key-env CODE_API_KEY \
  --model your-code-model \
  --out-dir runs/custom_code_case
```

DeepSeek 当前不支持 `json_schema` response_format，默认已经使用 `json_object`。如果切换到其他服务，也可以分别显式指定：

```bash
python3 solve_image_to_video.py 题目.png \
  --vision-json-mode json_object \
  --json-mode json_object \
  --out-dir runs/json_object_case
```

## 使用 Responses API

```bash
export OPENAI_API_KEY="你的 API key"

python3 solve_image_to_video.py 题目.png \
  --api-style responses \
  --model gpt-4.1 \
  --base-url https://api.openai.com/v1 \
  --api-key-env OPENAI_API_KEY \
  --out-dir runs/responses_case
```

## 当前 Manim 环境

```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate manim-ce-018
manim --version
```

已验证环境：

- conda env: `/opt/conda/envs/manim-ce-018`
- Manim Community: `0.18.0.post0`
- 中文字体：`Noto Sans CJK SC`
