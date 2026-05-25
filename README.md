# Manim Teach

Manim Teach 用于把一张题目图片自动转成中文解题讲解视频。当前包含两个入口：

- `web_app.py`：本地 Web 前端和薄 API 服务，支持拖拽上传图片、查看生成进度、播放输出视频，并在影院模式中边看边问。
- `solve_image_to_video.py`：后端生成脚本，调用模型 API 识别或整理题目，生成解题步骤、讲稿、Manim 分镜和 ManimCE 源码，然后在本地 Manim 环境中渲染出视频。

## 当前能力

- 输入单张题目图片。
- 提供 ChatGPT 风格的 Web 工作台，支持拖拽上传和对话式提交。
- 调用 DeepSeek、OpenAI 或 OpenAI-compatible API。
- 生成中文题目转写、解题步骤、口播讲稿、Manim 分镜和渲染说明。
- 生成完整 ManimCE Python 场景代码。
- 调用本地 conda 环境中的 Manim 渲染 MP4。
- 渲染失败时，将 Manim 日志发回模型，自动修复代码并重试。
- 输出视频后，可进入自定义全屏影院模式，右侧保留问答面板；发送问题时自动暂停视频。
- 支持 `dry-run` 只检查提示词，支持 `no-render` 只生成文件不渲染。

## 工作流程

```text
题目图片
  -> 复制到输出目录
  -> 构造多模态提示词
  -> 调用模型生成结构化 JSON
  -> 写出题目转写、解题稿、讲稿、分镜和 Manim 源码
  -> 校验 Manim 代码中的常见问题
  -> 调用 ManimCE 渲染视频
  -> 渲染失败时自动请求模型修复代码
  -> 写出最终视频路径
```

Web 服务和生成脚本都只依赖 Python 标准库；视频渲染依赖本机已有的 ManimCE conda 环境。

## 环境要求

- Python 3.8 或更高版本。
- 可访问的模型 API，默认使用 `https://api.deepseek.com`。
- API key 环境变量，默认读取 `DEEPSEEK_API_KEY`。
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
export DEEPSEEK_API_KEY="你的 API key"
```

如果使用兼容 OpenAI 接口的服务，也可以使用自定义环境变量：

```bash
export MODEL_API_KEY="你的 API key"
```

也可以在项目根目录创建 `.env`，后端脚本会自动读取：

```bash
DEEPSEEK_API_KEY="你的 API key"
MODEL_API_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-pro
MODEL_API_STYLE=chat
MODEL_API_KEY_ENV=DEEPSEEK_API_KEY
MODEL_INPUT_MODE=auto
```

### 2. 启动 Web 前端

```bash
python3 web_app.py --host 127.0.0.1 --port 7860
```

打开：

```text
http://127.0.0.1:7860
```

Web 前端会调用以下本地接口：

```text
GET  /api/health                    # 检查后端脚本是否存在
POST /api/jobs                      # 上传图片并创建生成任务
GET  /api/jobs/<job_id>             # 轮询任务状态
GET  /api/jobs/<job_id>/video       # 获取输出视频
GET  /api/jobs/<job_id>/artifact/*  # 读取生成文件
POST /api/chat                      # 视频问答接口，占位接通
```

上传后端会在后台执行 `solve_image_to_video.py`，任务目录写入：

```text
runs/web_jobs/<job_id>-<name>/output/
```

### 3. 直接运行后端完整流程

```bash
python3 solve_image_to_video.py 题目.png \
  --out-dir runs/case_001 \
  --model deepseek-v4-pro \
  --quality h
```

默认会执行完整流程：调用模型、写出中间文件、渲染视频、必要时自动修复 Manim 代码。

### 4. 查看结果

生成完成后，主要产物位于 `--out-dir` 指定目录：

```text
runs/case_001/
├── input.png                 # 复制后的输入图片
├── prompt.md                 # 本次发给模型的主提示词
├── run_config.json           # 本次运行配置
├── model_response.json       # 原始模型响应
├── generation.json           # 解析后的结构化生成结果
├── problem_transcript.md     # 图片题目转写
├── solution.md               # 中文解题步骤
├── lecture_script.md         # 中文视频讲稿
├── scenes.md                 # Manim 分镜规划
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
| `--model` | `deepseek-v4-pro` 或 `MODEL_NAME` | 模型名称 |
| `--base-url` | `https://api.deepseek.com` 或 `MODEL_API_BASE_URL` | 模型 API base URL |
| `--api-url` | 无 | 完整 API URL，设置后覆盖 base URL |
| `--api-style` | `chat` 或 `MODEL_API_STYLE` | `chat` 或 `responses` |
| `--api-key-env` | `DEEPSEEK_API_KEY` 或 `MODEL_API_KEY_ENV` | 读取 API key 的环境变量名 |
| `--json-mode` | `json_object` | `schema`、`json_object` 或 `none` |
| `--input-mode` | `auto` 或 `MODEL_INPUT_MODE` | `auto`、`image` 或 `text` |
| `--problem-text` | 无 | 直接传入题面文本，适合文本模型接口 |
| `--problem-text-file` | 自动查找同名 `.txt`/`.md` | 从文件读取题面文本 |
| `--max-tokens` | `12000` | 首轮生成最大输出 token |
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
  "lecture_script": "中文视频讲稿，按镜头顺序书写，适合口播。",
  "scenes_markdown": "Manim 分镜规划，包含每一幕的目的、视觉元素、动画和讲解要点。",
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

### DeepSeek 文本接口没有题面文本

默认 DeepSeek chat 接口不发送图片输入。如果没有提供题面文本，脚本会提示补充：

```bash
python3 solve_image_to_video.py 题目.png \
  --problem-text-file problem.md \
  --out-dir runs/deepseek_case
```

Web 前端中可以把题面文本粘贴到输入框，后端会写入 `problem.txt` 并通过 `--problem-text-file` 传给生成脚本。

### 模型返回不是合法 JSON

脚本会尽力修复常见 JSON 转义错误。如果仍然失败，会写出：

```text
raw_model_output.txt
api_error.txt
model_response.json
```

可尝试：

```bash
python3 solve_image_to_video.py 题目.png \
  --json-mode json_object \
  --out-dir runs/json_retry
```

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

其中 `web_app.py` 是当前前端入口，`solve_image_to_video.py` 是当前生成后端入口。

## 许可证

待定。
