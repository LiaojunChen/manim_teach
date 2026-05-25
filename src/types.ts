export type TaskStatus = 'idle' | 'generating' | 'ready'

export type Question = {
  id: string
  text: string
  frameDataUrl: string
  timestamp: number
  answer: string
}

export type Task = {
  id: string
  title: string
  createdAt: string
  imageUrl: string
  status: TaskStatus
  questions: Question[]
}

export type AskQuestionPayload = {
  text: string
  frameDataUrl: string
  timestamp: number
}
