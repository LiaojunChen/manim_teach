# Manim Teach Frontend

Claude-inspired interactive frontend for a "problem image to explanation video" workflow.

## Features

- Upload a problem image and simulate explanation video generation.
- Review task history in a left sidebar.
- Play or pause a canvas-based mock explanation video.
- Capture the paused frame automatically.
- Ask a follow-up question from a draggable floating panel.
- Store each follow-up with its frame, timestamp, question, and mock answer.

## Tech Stack

- React
- TypeScript
- Vite
- lucide-react

## Local Development

```bash
npm install
npm run dev
```

Open the local URL printed by Vite, usually `http://127.0.0.1:5173/`.

## Production Build

```bash
npm run build
```

## Backend Integration Points

Mock API functions live in `src/api.ts`:

- `generateVideoFromImage(file)`
- `askQuestionWithFrame(payload)`

Replace these functions when the real image-to-video and multimodal question-answering services are ready.
