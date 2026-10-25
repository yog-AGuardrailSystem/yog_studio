import { postJson } from './client'

export interface ModifyResult {
  patched_source: string
  diff: string
  guarded: string[]
  skipped: string[]
  already_guarded: string[]
  added_lines: number
  removed_lines: number
}

export const modify = (filename: string, source: string, tools: string[] = []) =>
  postJson<ModifyResult>('/modify', { filename, source, tools })

export async function downloadBundle(filename: string, source: string, policy_id: string, tools: string[] = []) {
  const res = await fetch('/api/modify/bundle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, source, policy_id, tools }),
  })
  if (!res.ok) {
    const j = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail))
  }
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = 'yog_patched_agent.zip'
  a.click()
  URL.revokeObjectURL(url)
}
