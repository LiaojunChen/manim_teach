# Manim Teach

Manim Teach 用于把一张题目图片自动转成中文解题讲解视频。当前推荐使用统一 Web 入口：

- `web_app.py`：统一启动前端和本地 API。它负责图片上传、任务管理、状态轮询、视频播放、生成文件查看和视频问答。
- `solve_image_to_video.py`：生成后端。Web API 会在后台调用它；也可以单独运行用于调试。

## 当前能力

- 输入单张题目图片。
- 提供 ChatGPT 风格的 Web 工作台，支持拖拽上传和对话式提交。
- 调用三段式模型链路：转写模型先做轻量 OCR，解题模型只生成精简解题稿，后端整理口播摘要和讲解结构，代码模型负责生成 ManimCE 源码。
- 转写阶段若强制 JSON 响应超时或不可解析，会自动关闭 `response_format` 重试一次。
- 代码模型超时、返回空内容或 JSON 不可解析时，会自动降级到内置 Manim 模板，保证仍能写出可渲染短版视频。
- 生成中文题目转写、解题步骤、口播摘要、讲解结构和渲染说明。
- 生成完整 ManimCE Python 场景代码。
- 调用本地 conda 环境中的 Manim 渲染 MP4。
- 渲染失败时，将 Manim 日志发回模型，自动修复代码并重试。
- 输出视频后，可进入自定义全屏影院模式，右侧保留问答面板；发送问题时自动暂停视频。
- 支持 `dry-run` 只检查提示词，支持 `no-render` 只生成文件不渲染。

## 工作流程

```text
题目图片
  -> 复制到输出目录
  -> 调用转写模型生成题面 JSON
  -> 调用解题模型生成精简解题稿 JSON
  -> 后端整理口播摘要和讲解结构
  -> 调用代码模型生成 Manim 源码 JSON
     -> 若代码模型失败，使用内置模板生成短版 Manim 源码
  -> 写出题目转写、解题稿、口播摘要、讲解结构和 Manim 源码
  -> 校验 Manim 代码中的常见问题
  -> 调用 ManimCE 渲染视频
  -> 渲染失败时自动请求模型修复代码
  -> 写出最终视频路径
```

前端、Web API 和生成脚本都只依赖 Python 标准库；视频渲染依赖本机已有的 ManimCE conda 环境。

## 环境要求

- Python 3.8 或更高版本。
- 可访问的转写/解题模型 API，默认使用 `https://right.codes/codex/v1` 的 `gpt-5.5`。
- 可访问的代码生成模型 API，默认使用 `https://api.deepseek.com` 的 `deepseek-v4-pro`。
- API key 环境变量，默认读取 `GPT55_API_KEY` 和 `DEEPSEEK_API_KEY`。
- conda 环境中已安装 Manim Community Edition。
- FFmpeg。
- LaTeX 环境，用于 Manim 的 `MathTex` 公式渲染。
- 中文字体，默认提示词要求使用 `Noto Sans CJK SC`。

当前脚本默认渲染环境：

```bash
conda env: manim-ce-018
conda bin: /opt/conda/bin/conda
Manim scene class: SolutionVideo
quality: h
```

检查 Manim 环境：

```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate manim-ce-018
manim --version
manim checkhealth
```

## 快速开始

### 1. 设置 API key

```bash
export GPT55_API_KEY="你的转写/解题模型 API key"
export DEEPSEEK_API_KEY="你的代码模型 API key"
```

如果使用兼容 OpenAI 接口的服务，也可以使用自定义环境变量：

```bash
export MODEL_API_KEY="你的 API key"
```

也可以在项目根目录创建 `.env`，后端脚本会自动读取：

```bash
DEEPSEEK_API_KEY="你的 API key"
GPT55_API_KEY="你的 API key"

VISION_MODEL_API_BASE_URL=https://right.codes/codex/v1
VISION_MODEL_NAME=gpt-5.5
VISION_MODEL_API_STYLE=chat
VISION_MODEL_API_KEY_ENV=GPT55_API_KEY
VISION_MODEL_JSON_MODE=json_object
VISION_INPUT_MODE=auto

CODE_MODEL_API_BASE_URL=https://api.deepseek.com
CODE_MODEL_NAME=deepseek-v4-pro
CODE_MODEL_API_STYLE=chat
CODE_MODEL_API_KEY_ENV=DEEPSEEK_API_KEY
CODE_MODEL_JSON_MODE=json_object
```

### 2. 启动 Web 前端

```bash
python3 web_app.py --host 127.0.0.1 --port 7860
```

打开：

```text
http://127.0.0.1:7860
```

Web 前端会调用以下本地接口，并由 `/api/jobs` 在后台启动 `solve_image_to_video.py`：

```text
GET  /api/health                    # 检查后端脚本是否存在
POST /api/jobs                      # 上传图片并创建生成任务
GET  /api/jobs/<job_id>             # 轮询任务状态
GET  /api/jobs/<job_id>/video       # 获取输出视频
GET  /api/jobs/<job_id>/artifact/*  # 读取生成文件
POST /api/chat                      # 视频问答接口，占位接通
```

上传后，任务目录写入：

```text
runs/web_jobs/<job_id>-<name>/output/
```

### 3. 直接调试生成后端

```bash
python3 solve_image_to_video.py 题目.png \
  --out-dir runs/case_001 \
  --vision-model gpt-5.5 \
  --model deepseek-v4-pro \
  --quality h
```

默认会执行完整流程：题面转写、精简解题、整理口播摘要/讲解结构、生成 Manim 代码、写出中间文件、渲染视频、必要时自动修复 Manim 代码。代码模型不可用时会自动使用模板兜底场景。

### 4. 查看结果

生成完成后，主要产物位于 `--out-dir` 指定目录：

```text
runs/case_001/
├── input.png                 # 复制后的输入图片
├── prompt.md                 # 首段转写提示词，兼容旧查看入口
├── transcript_prompt.md      # 题面转写提示词
├── solution_prompt.md        # 精简解题提示词
├── run_config.json           # 本次运行配置
├── model_response.json       # 原始模型响应
├── transcript_generation.json # 题面转写结构化结果
├── solution_generation.json  # 解题结果及后端整理出的口播摘要/讲解结构
├── code_generation.json      # Manim 代码结构化结果，可能来自模型或模板兜底
├── generation.json           # 解析后的结构化生成结果
├── problem_transcript.md     # 图片题目转写
├── solution.md               # 中文解题步骤
├── lecture_script.md         # 中文口播摘要
├── scenes.md                 # 简明讲解结构
├── render_notes.md           # 渲染说明和限制
├── video_scene.py            # 生成的 ManimCE 源码
├── render.log                # 首次渲染日志
├── video_path.txt            # 最终 mp4 路径
└── media/videos/.../*.mp4    # Manim 输出视频
```

如果发生自动修复，还会出现：

```text
repair_1_response.json
repair_1_summary.md
render_repair_1.log
repair_2_response.json
repair_2_summary.md
render_repair_2.log
```

## 常用命令

### 只生成文件，不渲染

适合先检查模型输出、讲稿和 Manim 源码：

```bash
python3 solve_image_to_video.py 题目.png \
  --out-dir runs/case_no_render \
  --model deepseek-v4-pro \
  --no-render
```

### 只生成提示词，不调用 API

适合检查提示词、输出目录和运行配置：

```bash
python3 solve_image_to_video.py 题目.png \
  --out-dir runs/case_dry_run \
  --dry-run
```

`dry-run` 会复制图片，并写出：

```text
prompt.md
run_config.json
```

### 使用 Responses API

```bash
export OPENAI_API_KEY="你的 API key"

python3 solve_image_to_video.py 题目.png \
  --base-url https://api.openai.com/v1 \
  --api-key-env OPENAI_API_KEY \
  --api-style responses \
  --model gpt-4.1 \
  --out-dir runs/responses_case
```

### 使用 OpenAI-compatible 服务

如果模型服务兼容 `/v1/chat/completions`：

```bash
export MODEL_API_KEY="你的 API key"

python3 solve_image_to_video.py 题目.png \
  --base-url https://openrouter.ai/api/v1 \
  --api-key-env MODEL_API_KEY \
  --model openai/gpt-4.1 \
  --out-dir runs/openrouter_case \
  --quality h
```

如果服务不支持 JSON Schema 结构化输出，可以降级为 JSON object：

```bash
python3 solve_image_to_video.py 题目.png \
  --base-url https://openrouter.ai/api/v1 \
  --api-key-env MODEL_API_KEY \
  --model openai/gpt-4.1 \
  --json-mode json_object \
  --out-dir runs/json_object_case
```

### 指定完整 API URL

`--api-url` 会覆盖 `--base-url` 和 `--api-style` 拼接逻辑：

```bash
python3 solve_image_to_video.py 题目.png \
  --api-url https://example.com/v1/chat/completions \
  --api-key-env MODEL_API_KEY \
  --model your-model-name \
  --out-dir runs/custom_api_case
```

### 调整 Manim 渲染环境

```bash
python3 solve_image_to_video.py 题目.png \
  --conda-bin /opt/conda/bin/conda \
  --conda-env manim-ce-018 \
  --quality m \
  --render-timeout 900 \
  --out-dir runs/render_case
```

质量参数支持：

```text
l / low / -ql       低清，适合调试
m / medium / -qm    中等质量
h / high / -qh      高清，默认
k / 4k / -qk        4K
```

## CLI 参数

```bash
python3 solve_image_to_video.py [-h] [options] image
```

核心参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `image` | 必填 | 题目图片路径 |
| `--out-dir` | `runs/<图片名>_<时间戳>` | 输出目录 |
| `--vision-model` | `gpt-5.5` 或 `VISION_MODEL_NAME` | 转写/解题模型名称 |
| `--vision-base-url` | `https://right.codes/codex/v1` 或 `VISION_MODEL_API_BASE_URL` | 转写/解题模型 API base URL |
| `--vision-api-key-env` | `GPT55_API_KEY` 或 `VISION_MODEL_API_KEY_ENV` | 转写/解题模型 API key 环境变量 |
| `--vision-json-mode` | `json_object` | 转写/解题模型结构化输出模式 |
| `--model` | `deepseek-v4-pro` 或 `CODE_MODEL_NAME` | Manim 代码模型名称 |
| `--base-url` | `https://api.deepseek.com` 或 `CODE_MODEL_API_BASE_URL` | 代码模型 API base URL |
| `--api-url` | 无 | 代码模型完整 API URL，设置后覆盖 base URL |
| `--api-style` | `chat` 或 `CODE_MODEL_API_STYLE` | 代码模型 API 风格 |
| `--api-key-env` | `DEEPSEEK_API_KEY` 或 `CODE_MODEL_API_KEY_ENV` | 代码模型 API key 环境变量 |
| `--json-mode` | `json_object` | 代码模型结构化输出模式 |
| `--input-mode` | `auto` 或 `VISION_INPUT_MODE` | `auto`、`image` 或 `text` |
| `--prefer-vision-over-text` | 默认开启 | 即使存在题面文本，也优先调用图片转写 |
| `--no-prefer-vision-over-text` | 关闭项 | 存在题面文本时不发送图片 |
| `--problem-text` | 无 | 直接传入题面文本，适合文本模型接口 |
| `--problem-text-file` | 自动查找同名 `.txt`/`.md` | 从文件读取题面文本 |
| `--max-tokens` | `6500` | 代码生成最大输出 token |
| `--ocr-max-tokens` | `2000` | 题面转写最大输出 token |
| `--vision-max-tokens` | `3000` | 解题最大输出 token |
| `--repair-max-tokens` | `9000` | 修复轮最大输出 token |
| `--temperature` | `0.2` | 模型采样温度 |
| `--api-timeout` | `300` | API 请求超时秒数 |
| `--scene-class` | `SolutionVideo` | 希望模型生成的 Manim 场景类名 |
| `--language` | `中文，简体中文讲解` | 解题、讲稿和屏幕文字语言 |
| `--conda-bin` | `/opt/conda/bin/conda` | conda 可执行文件路径 |
| `--conda-env` | `manim-ce-018` | 用于渲染的 conda 环境名 |
| `--quality` | `h` | Manim 渲染质量 |
| `--render-timeout` | `600` | 单次 Manim 渲染超时秒数 |
| `--max-repair-attempts` | `2` | 渲染失败后的模型修复次数 |
| `--no-render` | `False` | 只生成文件，不渲染 |
| `--dry-run` | `False` | 只创建输出目录和提示词 |

查看完整帮助：

```bash
python3 solve_image_to_video.py --help
```

## 生成内容格式

脚本要求模型返回结构化 JSON，并写入 `generation.json`。核心字段如下：

```json
{
  "problem_transcript": "题目图片的文字转写；若有不确定处，明确标出。",
  "solution_markdown": "中文 Markdown 解题步骤，包含关键公式和最终答案。",
  "lecture_script": "中文口播摘要，说明解题主线。",
  "scenes_markdown": "简明讲解结构，供代码生成或模板兜底使用。",
  "scene_class": "SolutionVideo",
  "manim_code": "完整可运行的 ManimCE Python 源码。",
  "render_notes": "渲染注意事项、已知限制、设计说明。"
}
```

渲染失败后的修复请求要求模型返回：

```json
{
  "scene_class": "SolutionVideo",
  "manim_code": "完整修复后的 ManimCE Python 源码。",
  "repair_summary": "中文简述修复了什么问题。"
}
```

## Manim 生成约束

脚本的提示词会要求模型遵守以下约束：

- 使用 Manim Community Edition，不使用 ManimGL。
- 源码必须包含 `from manim import *`。
- 默认生成继承 `Scene` 的场景类。
- 中文文本使用 `Text(..., font="Noto Sans CJK SC")` 或 `MarkupText`。
- 不把中文放进 `MathTex`。
- 数学公式使用 `MathTex`，复杂推导拆成多行。
- 使用 `VGroup`、`arrange`、`to_edge`、`next_to`、`align_to` 控制布局。
- 屏幕内容少而清晰，避免文字重叠和公式溢出。
- 可以使用同目录下复制后的输入图片，例如 `ImageMobject("input.png")`。
- 不依赖联网下载、外部素材或额外字体文件。
- 尽量兼容 ManimCE 0.18.x。

手动渲染已生成场景：

```bash
cd runs/case_001
conda run -n manim-ce-018 manim -pql video_scene.py SolutionVideo
```

如果 `generation.json` 中的 `scene_class` 不是 `SolutionVideo`，请使用实际类名。

## 错误处理

### 缺少 API key

如果看到类似错误：

```text
Missing API key. Set one of these environment variables...
```

请先设置：

```bash
export DEEPSEEK_API_KEY="你的 API key"
```

或使用：

```bash
export MODEL_API_KEY="你的 API key"
python3 solve_image_to_video.py 题目.png --api-key-env MODEL_API_KEY
```

### 读图接口没有收到图片或题面文本

如果选择了文本接口或关闭读图优先，需要提供题面文本：

```bash
python3 solve_image_to_video.py 题目.png \
  --problem-text-file problem.md \
  --out-dir runs/deepseek_case
```

Web 前端中可以把题面文本粘贴到输入框，后端会写入 `problem.txt` 并通过 `--problem-text-file` 传给生成脚本。默认配置下即使填写了题面文本，也仍会优先调用图片转写，并把文本作为补充上下文。

### 模型返回不是合法 JSON

脚本会尽力修复常见 JSON 转义错误。如果仍然失败，会写出：

```text
transcript_raw_model_output.txt
solution_raw_model_output.txt
code_raw_model_output.txt
*_api_error.txt
*_model_response.json
```

可尝试：

```bash
python3 solve_image_to_video.py 题目.png \
  --json-mode json_object \
  --out-dir runs/json_retry
```

### 代码模型失败或 Manim 渲染失败

如果代码模型超时、返回空内容或 JSON 不可解析，脚本不会直接中断，而会写入 `code_api_error.txt`，并用内置模板生成短版 `video_scene.py`。`render_notes.md` 中会记录兜底原因。

### Manim 渲染失败

脚本会自动重试修复，默认最多 2 次。相关文件包括：

```text
render.log
repair_1_summary.md
render_repair_1.log
repair_2_summary.md
render_repair_2.log
```

如果仍失败，优先检查：

- `video_scene.py` 是否包含不兼容 ManimCE 0.18.x 的 API。
- 中文是否被放进了 `MathTex`。
- 公式 LaTeX 是否缺少转义或括号。
- 页面内容是否过宽导致布局溢出。
- 本机是否安装 `Noto Sans CJK SC`。
- conda 环境是否能正常运行 `manim checkhealth`。

### 找不到生成视频

脚本会在 `media/videos` 下查找最新 MP4，并写入 `video_path.txt`。如果渲染显示成功但没有视频，请检查：

```bash
find runs/case_001/media/videos -name "*.mp4"
```

## 建议开发路线

当前脚本已经能跑通单文件端到端流程。后续可以逐步拆成更清晰的工程模块：

```text
src/manim_teach/
├── cli.py
├── config.py
├── prompts.py
├── model_client.py
├── artifacts.py
├── manim_validator.py
├── renderer.py
└── repair.py
```

推荐优先级：

1. 增加 `pyproject.toml`，把脚本封装成 `manim-teach` 命令。
2. 把提示词、schema、API 调用、渲染逻辑拆成独立模块。
3. 增加单元测试，覆盖 JSON 解析、类名清洗、质量参数映射和 Scene 类检测。
4. 增加示例图片和一次完整输出样例。
5. 增加人工审核步骤，允许在渲染前修订题目转写和解题稿。
6. 增加字幕、TTS、视频拼接和多题批处理。

## 项目文件

```text
.
├── README.md
├── web_app.py
├── web/
│   ├── index.html
│   └── static/
│       ├── app.js
│       └── styles.css
├── solve_image_to_video.py
└── README_solve_image_to_video.md
```

其中 `web_app.py` 是统一应用入口，`solve_image_to_video.py` 是生成后端入口。

## 许可证

待定。
