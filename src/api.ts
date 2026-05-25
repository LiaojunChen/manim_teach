import type { AskQuestionPayload } from './types'

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export async function generateVideoFromImage(file: File): Promise<{ taskTitle: string }> {
  await wait(1600)

  const cleanName = file.name
    .replace(/\.[^/.]+$/, '')
    .replace(/[-_]+/g, ' ')
    .trim()

  return {
    taskTitle: cleanName ? `${cleanName} 的解答视频` : '新题目的解答视频',
  }
}

export async function askQuestionWithFrame({
  text,
  timestamp,
}: AskQuestionPayload): Promise<{ answer: string }> {
  await wait(700)

  const minute = Math.floor(timestamp / 60)
  const second = Math.floor(timestamp % 60)
  const timeLabel = `${minute}:${second.toString().padStart(2, '0')}`

  return {
    answer: `已结合 ${timeLabel} 的画面继续解释：你问的“${text}”通常要先看当前步骤里的已知条件，再把它代回正在推导的式子。这里建议重点检查暂停帧中的关键量、单位和等号两侧是否保持一致。`,
  }
}
