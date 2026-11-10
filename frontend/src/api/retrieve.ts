import { postJson } from './client'

export interface Retrieved {
  id: string
  english: string
  tools_context: string[]
  gold_yog: string
  score: number
  relevant?: boolean
}

export const retrieve = (english: string, tools: string[], k = 3, mode?: 'real' | 'offline') =>
  postJson<{ results: Retrieved[] }>('/retrieve', { english, tools, k, mode }).then((r) => r.results)
