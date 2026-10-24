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
