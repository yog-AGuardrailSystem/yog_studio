import { getJson, postJson } from './client'
import type { ExplainResponse, PolicyRecord } from './types'

export const explain = (yog_source: string) => postJson<ExplainResponse>('/explain', { yog_source })

export const approve = (body: {
  yog_source: string
  english_rules: string[]
  retrieved_examples: string[]
  attempts: number
  evaluation?: Record<string, unknown> | null
}) => postJson<PolicyRecord>('/policies/approve', body)

export const reject = (reason: string) => postJson<{ status: string }>('/policies/reject', { reason })
export const listPolicies = () => getJson<PolicyRecord[]>('/policies')
export const getPolicy = (id: string) => getJson<PolicyRecord>(`/policies/${id}`)
