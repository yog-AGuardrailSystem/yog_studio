import { postJson } from './client'
import type { PolicyDraft, Tool } from './types'

export const translate = (english_rules: string[], tools: Tool[]) =>
  postJson<PolicyDraft>('/translate', { english_rules, tools })
