// Mirrors backend/app/core/models.py (CLAUDE.md section 9). Keep in sync.

export interface Param {
  name: string
  type_hint: string | null
  default: string | null
}

export interface Tool {
  name: string
  params: Param[]
  docstring: string | null
  source_line: number
  side_effect_hints: string[]
}

export interface DetectResult {
  kind: 'mcp_server' | 'function_calling_agent' | 'unknown'
  confidence: number
  evidence: string[]
}

export interface AnalyzeResponse {
  filename: string
  source: string
  detect: DetectResult
  tools: Tool[]
  candidates: Tool[]
}

export interface ClauseReadback {
  kind: string
  line: number
  text: string
}

export interface Readback {
  actions: { action: string; predicate: string; allow: string[]; deny: string[] }[]
  definitions: string[]
  facts: string[]
  inputs: string[]
  notes: string[]
  clauses: ClauseReadback[]
}

export interface ExplainResponse {
  valid: boolean
  errors: string[]
  readback: Readback | null
}

export interface PolicyRecord {
  id: string
  approved_at: string
  english_rules: string[]
  retrieved_examples: string[]
  attempts: number
  readback: string[]
  evaluation: Record<string, unknown> | null
  yog_source: string
}

export interface PolicyDraft {
  english_rules: string[]
  yog_source: string
  retrieved_examples: string[]
  attempts: number
  valid: boolean
  errors: string[]
  verified?: boolean | null
  attempt_log?: { n: number; compiled: boolean; errors: string[]; scenario_failures: string[] }[]
  grounded?: boolean                  // false: no retrieved example cleared the relevance floor
  cited_examples?: string[]           // examples the model said it used (checked against what was retrieved)
  citation_problems?: string[]
  floor?: number | null
  floor_calibrated?: boolean | null
  reranked?: boolean
  retrieved?: { id: string; english: string; score: number; source: string; relevant?: boolean; rerank?: number | null }[]
}
