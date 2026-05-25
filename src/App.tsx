import {
  ArrowUpRight,
  Bot,
  Clock3,
  FileImage,
  Grip,
  History,
  ImagePlus,
  Loader2,
  MessageSquareText,
  PanelLeft,
  Pause,
  Play,
  Plus,
  Send,
  Sparkles,
  Upload,
  X,
} from 'lucide-react'
import { type ChangeEvent, type PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { askQuestionWithFrame, generateVideoFromImage } from './api'
import type { Question, Task } from './types'
import './App.css'

const duration = 96

const makeId = () => crypto.randomUUID()

const formatTime = (value: number) => {
  const minute = Math.floor(value / 60)
  const second = Math.floor(value % 60)
  return `${minute}:${second.toString().padStart(2, '0')}`
}

const makePlaceholderImage = (title: string, accent: string) => {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="960" height="640" viewBox="0 0 960 640">
      <rect width="960" height="640" rx="28" fill="#f5f0e8"/>
      <rect x="56" y="54" width="848" height="532" rx="22" fill="#faf9f5" stroke="#e6dfd8" stroke-width="3"/>
      <text x="86" y="118" fill="#6c6a64" font-family="Inter, Arial" font-size="24">题目截图</text>
      <text x="86" y="198" fill="#141413" font-family="Georgia, serif" font-size="48">${title}</text>
      <path d="M96 278h768M96 352h596M96 426h704" stroke="#252523" stroke-width="12" stroke-linecap="round" opacity=".16"/>
      <circle cx="746" cy="448" r="66" fill="${accent}" opacity=".88"/>
      <path d="M716 450h60M746 420v60" stroke="#fff" stroke-width="10" stroke-linecap="round"/>
    </svg>
  `

  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

const seedTasks: Task[] = [
  {
    id: makeId(),
    title: '函数极值题解答视频',
    createdAt: '今天 03:42',
    imageUrl: makePlaceholderImage('f(x) = x² - 4x + 7', '#cc785c'),
    status: 'ready',
    questions: [
      {
        id: makeId(),
        text: '为什么这里要先配方？',
        frameDataUrl: makePlaceholderImage('暂停帧 0:38', '#5db8a6'),
        timestamp: 38,
        answer: '因为配方后顶点坐标会直接出现，后面判断最小值会更快，也更不容易漏掉定义域限制。',
      },
    ],
  },
  {
    id: makeId(),
    title: '几何辅助线思路',
    createdAt: '昨天 21:18',
    imageUrl: makePlaceholderImage('△ABC 辅助线', '#e8a55a'),
    status: 'ready',
    questions: [],
  },
]

type DragState = {
  startX: number
  startY: number
  originX: number
  originY: number
}

function App() {
  const [tasks, setTasks] = useState<Task[]>(seedTasks)
  const [activeTaskId, setActiveTaskId] = useState(seedTasks[0].id)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(32)
  const [capturedFrame, setCapturedFrame] = useState<string>('')
  const [questionText, setQuestionText] = useState('')
  const [isAsking, setIsAsking] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [questionPanelPos, setQuestionPanelPos] = useState({ x: 0, y: 0 })
  const [dragState, setDragState] = useState<DragState | null>(null)
  const [generationProgress, setGenerationProgress] = useState(0)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const uploadRef = useRef<HTMLInputElement | null>(null)
  const frameRef = useRef<number | null>(null)
  const lastTickRef = useRef<number | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)

  const activeTask = useMemo(
    () => tasks.find((task) => task.id === activeTaskId) ?? tasks[0],
    [activeTaskId, tasks],
  )

  const recentQuestions = activeTask?.questions ?? []
  const canUseVideo = activeTask?.status === 'ready'
  const shouldShowQuestionPanel = Boolean(canUseVideo && !isPlaying && capturedFrame)

  const drawFrame = useCallback(
    (time: number) => {
      const canvas = canvasRef.current
      const context = canvas?.getContext('2d')

      if (!canvas || !context || !activeTask) {
        return
      }

      const width = canvas.width
      const height = canvas.height
      const step = Math.min(1, time / duration)
      const phase = Math.floor(step * 5)
      const pulse = Math.sin(time * 0.18) * 0.5 + 0.5

      context.clearRect(0, 0, width, height)

      const gradient = context.createLinearGradient(0, 0, width, height)
      gradient.addColorStop(0, '#181715')
      gradient.addColorStop(0.58, '#252320')
      gradient.addColorStop(1, '#3a2a22')
      context.fillStyle = gradient
      context.fillRect(0, 0, width, height)

      context.fillStyle = '#faf9f5'
      context.font = '500 24px Inter, system-ui, sans-serif'
      context.fillText('AI 解答视频', 54, 62)

      context.fillStyle = '#a09d96'
      context.font = '400 18px Inter, system-ui, sans-serif'
      context.fillText(activeTask.title, 54, 94)

      context.strokeStyle = '#3b3832'
      context.lineWidth = 1
      context.strokeRect(54, 128, 358, 236)

      if (imageRef.current?.complete) {
        context.save()
        context.beginPath()
        context.rect(55, 129, 356, 234)
        context.clip()
        context.drawImage(imageRef.current, 55, 129, 356, 234)
        context.restore()
      } else {
        context.fillStyle = '#f5f0e8'
        context.fillRect(55, 129, 356, 234)
      }

      context.fillStyle = '#cc785c'
      context.globalAlpha = 0.22 + pulse * 0.16
      context.beginPath()
      context.arc(782 + pulse * 12, 226, 128, 0, Math.PI * 2)
      context.fill()
      context.globalAlpha = 1

      context.fillStyle = '#faf9f5'
      context.font = '400 42px Georgia, "Times New Roman", serif'
      context.fillText(['审题', '建模', '推导', '检验', '总结'][phase] ?? '总结', 522, 176)

      context.fillStyle = '#a09d96'
      context.font = '400 20px Inter, system-ui, sans-serif'
      context.fillText('当前步骤会随着播放推进，暂停后可围绕此帧追问。', 522, 216)

      const rows = [
        '1. 标记题目中的已知条件与目标量',
        '2. 选择最短的推导路径，避免跳步',
        '3. 把关键式子代回原题完成检验',
      ]

      rows.forEach((row, index) => {
        const y = 280 + index * 64
        context.fillStyle = index <= phase % 3 ? '#faf9f5' : '#a09d96'
        context.font = '500 22px Inter, system-ui, sans-serif'
        context.fillText(row, 522, y)

        context.fillStyle = index <= phase % 3 ? '#cc785c' : '#3b3832'
        context.fillRect(522, y + 20, 410 * Math.min(1, step * 1.4 + index * 0.08), 6)
      })

      context.fillStyle = '#252320'
      context.fillRect(54, 414, 1072, 118)

      context.fillStyle = '#5db8a6'
      context.beginPath()
      context.arc(86, 454, 6, 0, Math.PI * 2)
      context.fill()

      context.fillStyle = '#faf9f5'
      context.font = '400 20px "JetBrains Mono", ui-monospace, monospace'
      context.fillText(`frame.timestamp = "${formatTime(time)}"`, 110, 461)

      context.fillStyle = '#a09d96'
      context.font = '400 18px Inter, system-ui, sans-serif'
      context.fillText('暂停这一帧，系统会把画面与问题一起送入追问上下文。', 110, 496)

      context.fillStyle = '#faf9f5'
      context.fillRect(54, 584, 1072 * step, 8)
      context.fillStyle = '#cc785c'
      context.fillRect(54, 584, 1072 * step, 8)
    },
    [activeTask],
  )

  const captureFrame = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }

    setCapturedFrame(canvas.toDataURL('image/png'))
    setQuestionPanelPos((position) => {
      if (position.x || position.y) {
        return position
      }

      const panelWidth = 360
      const panelHeight = 440
      return {
        x: Math.max(20, window.innerWidth - panelWidth - 28),
        y: Math.max(86, Math.min(window.innerHeight - panelHeight - 20, 124)),
      }
    })
  }, [])

  const pausePlayback = useCallback(() => {
    if (!canUseVideo) {
      return
    }

    setIsPlaying(false)
    drawFrame(currentTime)
    captureFrame()
  }, [canUseVideo, captureFrame, currentTime, drawFrame])

  const playPlayback = () => {
    if (!canUseVideo) {
      return
    }

    setCapturedFrame('')
    setQuestionText('')
    setIsPlaying(true)
  }

  const togglePlayback = () => {
    if (isPlaying) {
      pausePlayback()
      return
    }

    playPlayback()
  }

  useEffect(() => {
    if (!activeTask) {
      return
    }

    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.onload = () => drawFrame(currentTime)
    image.src = activeTask.imageUrl
    imageRef.current = image
  }, [activeTask, currentTime, drawFrame])

  useEffect(() => {
    if (!activeTask) {
      return
    }

    drawFrame(currentTime)
  }, [activeTask, currentTime, drawFrame])

  useEffect(() => {
    if (!isPlaying) {
      lastTickRef.current = null
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current)
      }
      return
    }

    const tick = (timestamp: number) => {
      if (lastTickRef.current === null) {
        lastTickRef.current = timestamp
      }

      const delta = (timestamp - lastTickRef.current) / 1000
      lastTickRef.current = timestamp

      setCurrentTime((value) => {
        const next = value + delta
        return next >= duration ? 0 : next
      })

      frameRef.current = requestAnimationFrame(tick)
    }

    frameRef.current = requestAnimationFrame(tick)

    return () => {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current)
      }
    }
  }, [isPlaying])

  useEffect(() => {
    if (activeTask?.status !== 'generating') {
      return
    }

    const interval = window.setInterval(() => {
      setGenerationProgress((value) => Math.min(96, value + 7))
    }, 150)

    return () => window.clearInterval(interval)
  }, [activeTask?.status])

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''

    if (!file) {
      return
    }

    const imageUrl = URL.createObjectURL(file)
    const id = makeId()
    const newTask: Task = {
      id,
      title: '正在生成解答视频',
      createdAt: '刚刚',
      imageUrl,
      status: 'generating',
      questions: [],
    }

    setTasks((items) => [newTask, ...items])
    setActiveTaskId(id)
    setIsPlaying(false)
    setCapturedFrame('')
    setCurrentTime(0)
    setSidebarOpen(false)

    const result = await generateVideoFromImage(file)
    setTasks((items) =>
      items.map((task) =>
        task.id === id
          ? {
              ...task,
              title: result.taskTitle,
              status: 'ready',
            }
          : task,
      ),
    )
    setGenerationProgress(100)
  }

  const handleSubmitQuestion = async () => {
    const text = questionText.trim()

    if (!text || !activeTask || !capturedFrame || isAsking) {
      return
    }

    setIsAsking(true)
    const response = await askQuestionWithFrame({
      text,
      frameDataUrl: capturedFrame,
      timestamp: currentTime,
    })

    const question: Question = {
      id: makeId(),
      text,
      frameDataUrl: capturedFrame,
      timestamp: currentTime,
      answer: response.answer,
    }

    setTasks((items) =>
      items.map((task) =>
        task.id === activeTask.id
          ? {
              ...task,
              questions: [question, ...task.questions],
            }
          : task,
      ),
    )
    setQuestionText('')
    setIsAsking(false)
  }

  const selectTask = (id: string) => {
    setActiveTaskId(id)
    setIsPlaying(false)
    setCapturedFrame('')
    setQuestionText('')
    setGenerationProgress(0)
    setCurrentTime(26)
    setSidebarOpen(false)
  }

  const resetToNewTask = () => {
    setActiveTaskId('')
    setIsPlaying(false)
    setCapturedFrame('')
    setQuestionText('')
    setGenerationProgress(0)
    setCurrentTime(0)
    setSidebarOpen(false)
  }

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    setDragState({
      startX: event.clientX,
      startY: event.clientY,
      originX: questionPanelPos.x,
      originY: questionPanelPos.y,
    })
  }

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragState) {
      return
    }

    const width = 360
    const height = 460
    const nextX = dragState.originX + event.clientX - dragState.startX
    const nextY = dragState.originY + event.clientY - dragState.startY

    setQuestionPanelPos({
      x: Math.max(12, Math.min(window.innerWidth - width - 12, nextX)),
      y: Math.max(72, Math.min(window.innerHeight - height - 12, nextY)),
    })
  }

  const handlePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.releasePointerCapture(event.pointerId)
    setDragState(null)
  }

  return (
    <div className="app-shell">
      <aside className={`history-rail ${sidebarOpen ? 'is-open' : ''}`} aria-label="历史记录">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            ✣
          </span>
          <div>
            <strong>Claude Study</strong>
            <span>题目到解答视频</span>
          </div>
        </div>

        <button className="new-task-button" type="button" onClick={() => uploadRef.current?.click()}>
          <Plus size={17} />
          新建题目
        </button>

        <button className="ghost-button mobile-new" type="button" onClick={resetToNewTask}>
          <ImagePlus size={16} />
          空白上传
        </button>

        <div className="rail-section-title">
          <History size={15} />
          最近记录
        </div>

        <div className="history-list">
          {tasks.map((task) => (
            <button
              className={`history-item ${task.id === activeTaskId ? 'is-active' : ''}`}
              key={task.id}
              type="button"
              onClick={() => selectTask(task.id)}
            >
              <span className="history-title">{task.title}</span>
              <span className="history-meta">
                <Clock3 size={13} />
                {task.createdAt}
                <span className={`status-dot status-${task.status}`}>{task.status === 'ready' ? '已生成' : '生成中'}</span>
              </span>
            </button>
          ))}
        </div>
      </aside>

      {!shouldShowQuestionPanel && (
        <button className="mobile-menu-button" type="button" onClick={() => setSidebarOpen(true)} aria-label="打开历史记录">
          <PanelLeft size={18} />
        </button>
      )}

      {sidebarOpen && <button className="rail-scrim" type="button" aria-label="关闭历史记录" onClick={() => setSidebarOpen(false)} />}

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <span className="eyebrow">
              <Sparkles size={14} />
              Frame-aware tutor
            </span>
            <h1>{activeTask?.title ?? '上传一道题，生成可追问的解答视频'}</h1>
          </div>
          <div className="header-actions">
            <button className="secondary-button" type="button" onClick={resetToNewTask}>
              <ImagePlus size={16} />
              新题目
            </button>
            <button className="primary-button" type="button" onClick={() => uploadRef.current?.click()}>
              <Upload size={16} />
              上传图片
            </button>
          </div>
        </header>

        <input ref={uploadRef} className="visually-hidden" type="file" accept="image/*" onChange={handleUpload} />

        <section className="studio-grid">
          <div className="left-stack">
            <section className="upload-panel" aria-label="题目输入">
              <div className="panel-heading">
                <div>
                  <span className="section-kicker">Input</span>
                  <h2>题目图片</h2>
                </div>
                <span className="soft-badge">{activeTask?.status === 'generating' ? '生成中' : activeTask ? '已载入' : '等待上传'}</span>
              </div>

              {activeTask ? (
                <div className="problem-preview">
                  <img src={activeTask.imageUrl} alt="当前题目预览" />
                </div>
              ) : (
                <button className="drop-zone" type="button" onClick={() => uploadRef.current?.click()}>
                  <FileImage size={26} />
                  <span>点击上传题目截图</span>
                  <small>支持图片文件，当前版本会模拟生成解答视频。</small>
                </button>
              )}
            </section>

            <section className="question-log" aria-label="追问记录">
              <div className="panel-heading">
                <div>
                  <span className="section-kicker">Follow-up</span>
                  <h2>暂停帧追问</h2>
                </div>
                <span className="soft-badge">{recentQuestions.length} 条</span>
              </div>

              {recentQuestions.length > 0 ? (
                <div className="log-list">
                  {recentQuestions.map((question) => (
                    <article className="log-item" key={question.id}>
                      <img src={question.frameDataUrl} alt={`暂停帧 ${formatTime(question.timestamp)}`} />
                      <div>
                        <span>{formatTime(question.timestamp)}</span>
                        <strong>{question.text}</strong>
                        <p>{question.answer}</p>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-log">
                  <MessageSquareText size={20} />
                  <p>播放解答视频并暂停，系统会抓取当前帧，再把你的问题记录在这里。</p>
                </div>
              )}
            </section>
          </div>

          <section className="video-stage" aria-label="解答视频">
            <div className="video-topbar">
              <div>
                <span className="section-kicker">Output</span>
                <h2>解答视频</h2>
              </div>
              <span className={`video-state ${isPlaying ? 'is-playing' : ''}`}>
                {isPlaying ? '播放中' : canUseVideo ? '暂停可提问' : '等待生成'}
              </span>
            </div>

            <div className={`video-card ${activeTask?.status === 'generating' ? 'is-generating' : ''}`}>
              {activeTask?.status === 'generating' && (
                <div className="generation-overlay">
                  <Loader2 className="spin" size={28} />
                  <strong>正在把题目拆成解答步骤</strong>
                  <p>模拟生成中，稍后会得到一个可暂停追问的视频。</p>
                  <div className="progress-track">
                    <span style={{ width: `${generationProgress}%` }} />
                  </div>
                </div>
              )}

              {!activeTask && (
                <div className="video-empty">
                  <Bot size={36} />
                  <strong>还没有题目</strong>
                  <p>上传一张题目截图后，这里会生成解答视频。</p>
                </div>
              )}

              <canvas
                ref={canvasRef}
                className="solution-canvas"
                width="1180"
                height="664"
                aria-label="模拟解答视频画面"
                onClick={togglePlayback}
              />

              {canUseVideo && (
                <button className="center-play-button" type="button" onClick={togglePlayback} aria-label={isPlaying ? '暂停视频' : '播放视频'}>
                  {isPlaying ? <Pause size={24} /> : <Play size={24} />}
                </button>
              )}
            </div>

            <div className="player-controls">
              <button className="control-button" type="button" disabled={!canUseVideo} onClick={togglePlayback}>
                {isPlaying ? <Pause size={18} /> : <Play size={18} />}
                {isPlaying ? '暂停并提问' : '播放'}
              </button>
              <div className="timeline" aria-label="播放进度">
                <span style={{ width: `${Math.min(100, (currentTime / duration) * 100)}%` }} />
              </div>
              <span className="time-label">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
          </section>
        </section>
      </main>

      {shouldShowQuestionPanel && (
        <section
          className="floating-question"
          style={{ transform: `translate3d(${questionPanelPos.x}px, ${questionPanelPos.y}px, 0)` }}
          aria-label="暂停帧提问窗"
        >
          <div
            className="floating-titlebar"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
          >
            <Grip size={16} />
            <span>基于暂停帧提问</span>
            <button
              type="button"
              aria-label="关闭提问窗"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation()
                setCapturedFrame('')
              }}
            >
              <X size={15} />
            </button>
          </div>

          <img className="captured-frame" src={capturedFrame} alt={`暂停帧 ${formatTime(currentTime)}`} />

          <div className="frame-context">
            <span>{formatTime(currentTime)}</span>
            <p>当前画面和你的问题会作为同一组输入，后续可直接替换为真实多模态问答接口。</p>
          </div>

          <label className="question-input-label" htmlFor="frame-question">
            想问这一步什么？
          </label>
          <textarea
            id="frame-question"
            value={questionText}
            onChange={(event) => setQuestionText(event.target.value)}
            placeholder="例如：为什么这里可以直接代入这个条件？"
          />
          <button className="primary-button full-width" type="button" disabled={!questionText.trim() || isAsking} onClick={handleSubmitQuestion}>
            {isAsking ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
            {isAsking ? '正在回答' : '发送追问'}
          </button>
        </section>
      )}

      <a className="source-link" href="https://getdesign.md/claude/design-md" target="_blank" rel="noreferrer">
        Claude design-md
        <ArrowUpRight size={14} />
      </a>
    </div>
  )
}

export default App
