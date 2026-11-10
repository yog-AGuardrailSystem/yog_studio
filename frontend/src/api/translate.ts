import { postJson } from './client'
import type { PolicyDraft, Tool } from './types'

export const translate = (english_rules: string[], tools: Tool[], mode?: 'real' | 'offline', rerank = false) =>
  postJson<PolicyDraft>('/translate', { english_rules, tools, mode, rerank })
