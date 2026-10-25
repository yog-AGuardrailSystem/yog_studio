import { postJson } from './client'

export interface CheckRequest {
  policy: string
  actor: string
  action: string
  resource: string
  context: string[]
}

export interface CheckResult {
  decision: 'ALLOW' | 'DENY'
  reason: string
  trace: string[]
}

export const check = (req: CheckRequest) => postJson<CheckResult>('/check', req)
