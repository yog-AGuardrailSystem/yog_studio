import { postJson } from './client'
import type { Tool } from './types'

export interface Scenario {
  actor: string
  action: string
  resource: string
  context: string[]
  expected: 'ALLOW' | 'DENY'
  source: 'generated' | 'user'
  unconfirmed: boolean
  note: string
}

export interface ScenarioResult extends Scenario {
  actual: 'ALLOW' | 'DENY' | null
  reason: string
  trace: string[]
  passed: boolean
  error: string | null
}

export interface EvalSummary {
  independent_total: number
  independent_passed: number
  pass_pct: number | null
  unconfirmed: number
  errors: number
  all_green: boolean
}

export interface EvalReport {
  results: ScenarioResult[]
  summary: EvalSummary
  warnings: string[]
}

export const evaluate = (body: {
  yog_source: string
  english_rules: string[]
  tools: Tool[]
  user_scenarios: Scenario[]
  use_llm?: boolean
}) => postJson<EvalReport>('/evaluate', body)
