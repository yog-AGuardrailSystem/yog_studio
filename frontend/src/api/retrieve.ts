import { postJson } from './client'

export interface Retrieved {
  id: string
  english: string
  tools_context: string[]
  gold_yog: string
  score: number
}

export const retrieve = (english: string, tools: string[], k = 3) =>
  postJson<{ results: Retrieved[] }>('/retrieve', { english, tools, k }).then((r) => r.results)
