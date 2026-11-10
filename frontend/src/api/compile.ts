import { getJson, postJson } from './client'
import type { PolicyDraft } from './types'

export interface Diagnostic {
  code: string
  severity: 'error' | 'warning'
  line: number | null
  message: string
  hint?: string | null
  suggestion?: string | null
  fix?: { line: number; find: string; replace: string } | null
}
export interface TokenInfo { kind: string; value: string | number | null; line: number }
export interface PredicateInfo { name: string; arity: number; role: 'fact' | 'rule' | 'decision'; clauses: number; line: number | null }
export interface CompileInfo {
  ok: boolean
  diagnostics: Diagnostic[]
  tokens: TokenInfo[]
  ast: { facts?: unknown[]; clauses?: unknown[]; queries?: unknown[] } | null
  predicates: PredicateInfo[]
}
export interface QueryResult {
  line: number
  text: string
  kind: 'decision' | 'fact-query' | 'unsupported'
  decision: 'ALLOW' | 'DENY' | null
  answer: boolean | null
  reason: string
  trace: string[]
  bindings: Record<string, unknown>[]
  expected: 'ALLOW' | 'DENY' | null
  passed: boolean | null
}
export interface AdHoc { actor: string; action: string; resource: string; context: string[] }
export interface RunResponse {
  ok: boolean
  diagnostics: Diagnostic[]
  results: QueryResult[]
  passed: number
  failed: number
  untested: number
  truncated: boolean
  adhoc: { decision: 'ALLOW' | 'DENY'; reason: string; trace: string[] } | null
  adhoc_error: string | null
}
export interface CLexerResponse {
  available: boolean
  matched?: boolean
  [k: string]: unknown
}
export interface TeamGroup { id: string; title: string; english: string; source: string; queries: number; uses_context: boolean }
export interface Info {
  provider: string; model: string | null; offline_demo: boolean; engine: string; c_lexer: boolean; commit: string
  default_mode: 'real' | 'offline'
  live_available: boolean; live_allowed: boolean; live_ready: boolean; live_reason: string | null; live_provider: string | null
}
export interface Retrieved {
  id: string; english: string; tools_context: string[]; gold_yog: string; score: number; source: string
  relevant?: boolean; lexical?: number; rerank?: number | null
}
export interface RetrieveResult { results: Retrieved[]; floor: number | null; floor_calibrated: boolean | null; grounded: boolean; provider: string | null }
export type Mode = 'real' | 'offline'
export interface Readback {
  actions: { action: string; predicate: string; allow: string[]; deny: string[] }[]
  definitions: string[]
  facts: string[]
  inputs: string[]
  notes: string[]
  clauses: { kind: string; line: number; text: string }[]
}
export interface JobView {
  id: string
  status: 'running' | 'done' | 'error' | 'cancelled'
  events: Record<string, unknown>[]
  next: number
  result: PolicyDraft | null
  error: string | null
}

export const compile = (source: string) => postJson<CompileInfo>('/compile', { source })
export const runProgram = (source: string, adhoc?: AdHoc) => postJson<RunResponse>('/run', { source, adhoc })
export const compareCLexer = (source: string) => postJson<CLexerResponse>('/compile/c-lexer', { source })
export const teamExamples = () => getJson<TeamGroup[]>('/examples/team')
export const getInfo = () => getJson<Info>('/info')
export const retrieve = (english: string, tools: string[] = [], k = 3, mode?: Mode) =>
  postJson<RetrieveResult>('/retrieve', { english, tools, k, mode })
export const explain = (yog_source: string) =>
  postJson<{ valid: boolean; errors: string[]; readback: Readback | null }>('/explain', { yog_source })
export const startTranslate = (english_rules: string[], opts: { mode?: Mode; rerank?: boolean } = {}) =>
  postJson<{ job_id: string }>('/translate/start', { english_rules, tools: [], mode: opts.mode, rerank: !!opts.rerank })
export const pollTranslate = (id: string, since: number) => getJson<JobView>(`/translate/${id}?since=${since}`)
export const cancelTranslate = (id: string) => postJson<{ cancelled: boolean }>(`/translate/${id}/cancel`, {})
export const benchmarkLatest = () =>
  getJson<{ evaluation: Record<string, any> | null; retrieval: Record<string, any> | null; note: string | null }>('/benchmark/latest')
