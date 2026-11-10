import { getJson, postJson } from './client'
import type { PolicyRecord } from './types'

/** Which policy a tool works on. `policy_id: "demo"` is the built-in demo; `source` is pasted text; neither = latest approved. */
export interface PolicyRef {
  policy_id?: string | null
  source?: string | null
}

export type Decision = 'ALLOW' | 'DENY'

// ---- Why-Explainer
export interface WhyStep { text: string; ok: boolean | null; note: string }
export interface ClauseWhy {
  kind: 'allow' | 'deny'
  line: number
  head: string
  status: 'matched' | 'failed' | 'head_mismatch' | 'error'
  steps: WhyStep[]
  failed_at: number | null
}
export interface WhyResult {
  decision: Decision
  reason: string
  verdict: string
  winner_line: number | null
  clauses: ClauseWhy[]
  context: string[]
  error: boolean
}
export interface WhyResponse { policy_label: string; source: string; result: WhyResult; consistent: boolean }
export const why = (ref: PolicyRef, actor: string, action: string, resource: string, context: string[]) =>
  postJson<WhyResponse>('/studio/why', { ...ref, actor, action, resource, context })

// ---- Policy Map
export interface Axis { kind: 'hour' | 'day' | 'arg'; tool?: string; param?: string; values?: number[] }
export interface MapSuggest {
  policy_label: string
  actions: string[]
  actors: string[]
  resources: string[]
  uses_hour: boolean
  uses_day: boolean
  arg_keys: { tool: string; param: string; values: number[] }[]
}
export interface MapResult {
  policy_label: string
  x_title: string
  y_title: string
  x_labels: string[]
  y_labels: string[]
  cells: ('A' | 'D')[][]
  reasons: string[][]
  allow: number
  deny: number
}
export const mapSuggest = (ref: PolicyRef) => postJson<MapSuggest>('/studio/map/suggest', ref)
export const policyMap = (ref: PolicyRef, body: { actor: string; action: string; resource: string; context: string[]; x: Axis; y: Axis | null }) =>
  postJson<MapResult>('/studio/map', { ...ref, ...body })

// ---- Gap Analyzer
export interface TestCase { actor: string; action: string; resource: string; context: string[]; expected: Decision }
export interface Finding {
  id: string
  severity: 'warning' | 'info'
  certainty: 'proved' | 'heuristic'
  title: string
  detail: string
  lines: number[]
  action: string | null
}
export interface GapReport {
  policy_label: string
  source: string
  findings: Finding[]
  governed: number
  total: number
  coverage_pct: number | null
  clauses: { line: number; kind: 'allow' | 'deny'; head: string; matched: number; tried: number }[]
  clause_coverage_pct: number | null
  probes: number
}
export const gaps = (ref: PolicyRef, tools: string[], scenarios: TestCase[] = []) => postJson<GapReport>('/studio/gaps', { ...ref, tools, scenarios })

// ---- Red-Team
export interface Invariant {
  action: string
  must: Decision
  hour_min?: number | null
  hour_max?: number | null
  arg?: { tool: string; param: string; min?: number | null; max?: number | null } | null
}
export interface Attack {
  family: string
  note: string
  actor: string
  action: string
  resource: string
  context: string[]
  decision: Decision
  reason: string
  violates: number | null
  suspicious: boolean
}
export interface RedTeamReport {
  policy_label: string
  checked: number
  counterexamples: number
  suspicious: number
  families: { family: string; total: number; allowed: number }[]
  attacks: Attack[]
  invariants: string[]
  note: string
}
export const redTeam = (ref: PolicyRef, invariants: Invariant[]) => postJson<RedTeamReport>('/studio/redteam', { ...ref, invariants })

// ---- Test Strength
export interface Mutant {
  id: number
  line: number
  kind: string
  description: string
  before: string
  after: string
  status: 'killed' | 'survived' | 'invalid'
  caught_by: string | null
}
export interface MutationReport {
  policy_label: string
  tests_used: number
  tests_source: 'yours' | 'baseline'
  tests_excluded: number
  valid: number
  killed: number
  survived: number
  invalid: number
  score: number | null
  mutants: Mutant[]
  note: string
}
export const mutation = (ref: PolicyRef, scenarios: TestCase[]) => postJson<MutationReport>('/studio/mutation', { ...ref, scenarios })

// ---- Templates
export interface Template {
  id: string
  pack: string
  pack_title: string
  english: string
  tools_context: string[]
  source_label: string
  reviewed: boolean
  yog: string
  scenarios: number
}
export interface CombineResult { ok: boolean; source: string; errors: string[]; used: string[] }
export const templates = () => getJson<Template[]>('/studio/templates')
export const combineTemplates = (ids: string[]) => postJson<CombineResult>('/studio/templates/combine', { ids })

// ---- Version history
export interface VersionSummary {
  id: string
  approved_at: string
  note: string
  parent_id: string | null
  restored_from: string | null
  clauses: number
  rules: number
  pass_pct: number | null
  latest: boolean
}
export interface Flip { actor: string; action: string; resource: string; context: string[]; before: Decision; after: Decision }
export interface DiffResult {
  a: string
  b: string
  text_diff: string
  added: number
  removed: number
  probes: number
  flips: Flip[]
  flips_total: number
  changed_actions: string[]
  summary: string
}
export const versions = () => getJson<VersionSummary[]>('/studio/versions')
export const diffVersions = (a: string, b: string) => postJson<DiffResult>('/studio/versions/diff', { a, b })
export const restoreVersion = (policy_id: string, note: string) => postJson<PolicyRecord>('/studio/versions/restore', { policy_id, note })

// ---- Audit log
export interface AuditEntry {
  seq: number
  at: string
  tool: string
  args: Record<string, unknown>
  sim_hour: number
  sim_day: string
  guarded: boolean
  decision: 'ALLOW' | 'DENY' | 'UNGUARDED'
  reason: string
  executed: boolean
  policy_id: string | null
  hash: string
}
export const auditList = (p: { decision?: string; tool?: string; q?: string; limit?: number } = {}) => {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== '') qs.set(k, String(v))
  return getJson<{ entries: AuditEntry[]; total: number }>(`/studio/audit?${qs}`)
}
export const auditVerify = () => getJson<{ ok: boolean; checked: number; total: number; bad_seq: number | null; problem: string }>('/studio/audit/verify')
export const AUDIT_CSV_URL = '/api/studio/audit/export.csv'

// ---- Trace Replay
export interface ReplayRow {
  n: number
  tool: string
  args: Record<string, unknown>
  hour: number
  day: string
  decision: Decision
  reason: string
  other: Decision | null
  other_reason: string
  changed: boolean
}
export interface ReplayResult {
  policy_label: string
  other_label: string | null
  rows: ReplayRow[]
  summary: { total: number; allowed: number; denied: number; other_allowed: number | null; changed: number }
  problems: string[]
}
export const replaySample = () => getJson<{ filename: string; format: string; text: string }>('/studio/replay/sample')
export const replay = (policy: PolicyRef, compare: PolicyRef | null, text: string, format: 'jsonl' | 'csv' | 'audit') =>
  postJson<ReplayResult>('/studio/replay', { policy, compare, text, format })

// ---- Runtime Guard
export const sdkRuntime = () => getJson<{ filename: string; source: string; lines: number }>('/studio/sdk/runtime')
export interface TryResult {
  policy_label: string
  decision: Decision
  reason: string
  action: string
  resource: string
  context: string[]
  policy_sha256: string
}
export const sdkTry = (ref: PolicyRef, tool: string, args: Record<string, unknown>, hour: number, day: string) =>
  postJson<TryResult>('/studio/sdk/try', { ...ref, tool, args, hour, day })

// ---- Export Pack
export const exportPreview = (policy_id: string, source: string | null, filename: string) =>
  postJson<{ ok: boolean; reason: string; files: string[]; policy_id?: string }>('/studio/export/preview', { policy_id, source, filename })
export async function exportPack(policy_id: string, source: string | null, filename: string, tools: string[]): Promise<Blob> {
  const res = await fetch('/api/studio/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ policy_id, source, filename, tools }),
  })
  if (!res.ok) {
    let msg = res.statusText
    try { const b = await res.json(); msg = typeof b.detail === 'string' ? b.detail : JSON.stringify(b.detail) } catch { /* not JSON */ }
    throw new Error(msg)
  }
  return res.blob()
}

// ---- Scorecard
export interface Metric { id: string; label: string; value: string | null; detail: string; status: 'good' | 'warn' | 'bad' | 'todo'; link: string }
export interface Scorecard { policy_label: string; headline: string; metrics: Metric[] }
export const scorecard = (ref: PolicyRef, tools: string[], include_strength = true) =>
  postJson<Scorecard>('/studio/scorecard', { ...ref, tools, include_strength })
