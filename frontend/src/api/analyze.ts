import { getJson, postForm, postJson } from './client'
import type { AnalyzeResponse } from './types'

export const analyzeSource = (filename: string, source: string) =>
  postJson<AnalyzeResponse>('/analyze', { filename, source })

export const analyzeUpload = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return postForm<AnalyzeResponse>('/analyze/upload', form)
}

export const listSamples = () => getJson<string[]>('/samples/agents')
export const getSample = (name: string) => getJson<{ filename: string; source: string }>(`/samples/agents/${name}`)

export const getDemoPolicy = () =>
  getJson<{ yog_source: string; english_rules: string[]; note: string }>('/samples/demo-policy')
