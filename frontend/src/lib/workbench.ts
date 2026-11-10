import type { Diagnostic, QueryResult } from '../api/compile'

/** Lines of the program that decided a request, found from the engine's own reason and trace (nothing guessed). */
export function traceLines(source: string, reason: string, trace: string[]): { deciding: number | null; support: number[] } {
  const m = /line (\d+)/.exec(reason)
  const deciding = m ? Number(m[1]) : null
  const norm = (s: string) => s.replace(/\s+/g, '').toLowerCase()
  const lines = source.split('\n')
  const support = new Set<number>()
  for (const t of trace) {
    const f = /matched fact (.+)$/.exec(t.trim())
    if (!f) continue
    const want = 'fact' + norm(f[1])
    lines.forEach((ln, i) => {
      if (norm(ln.split('#')[0]) === want) support.add(i + 1)
    })
  }
  if (deciding) support.delete(deciding)
  return { deciding, support: [...support] }
}

/** Apply a diagnostic's machine-applicable fix: replace `find` with `replace` on that line. Null if it no longer applies. */
export function applyFix(source: string, d: Diagnostic): string | null {
  if (!d.fix) return null
  const lines = source.split('\n')
  const i = d.fix.line - 1
  if (i < 0 || i >= lines.length || !lines[i].includes(d.fix.find)) return null
  lines[i] = lines[i].replace(d.fix.find, d.fix.replace)
  return lines.join('\n')
}

export function encodeShare(source: string): string {
  const bytes = new TextEncoder().encode(source)
  let bin = ''
  bytes.forEach((b) => (bin += String.fromCharCode(b)))
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function decodeShare(code: string): string | null {
  try {
    const b64 = code.replace(/-/g, '+').replace(/_/g, '/')
    const bin = atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4))
    return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)))
  } catch {
    return null
  }
}

export const shareUrl = (source: string) => `${location.origin}/studio/workbench#p=${encodeShare(source)}`

export function sourceFromHash(hash: string): string | null {
  const m = /[#&]p=([A-Za-z0-9_-]+)/.exec(hash)
  return m ? decodeShare(m[1]) : null
}

export function safeGet(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
export function safeSet(key: string, v: string): void {
  try { localStorage.setItem(key, v) } catch { /* private mode: autosave is a convenience only */ }
}

export function downloadText(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

export const decisionPredicates = (q: { name: string; role: string }[]) => q.filter((p) => p.role === 'decision').map((p) => p.name)

export const resultLabel = (r: QueryResult) =>
  r.kind === 'decision' ? r.decision : r.kind === 'fact-query' ? (r.answer ? 'TRUE' : 'FALSE') : 'n/a'

export const STARTER = `# Welcome to YOG. Edit me: the right-hand tabs update as you type.
fact role(alice, admin)
fact role(bob, viewer)
fact environment(db1, production)

rule is_prod(R):
    environment(R, production)

allow can_delete(User, Res):
    role(User, admin)

deny can_delete(User, Res):
    is_prod(Res)
    not role(User, admin)

query can_delete(alice, db1)   # admin may delete -> ALLOW
query can_delete(bob, db1)     # viewer, production -> DENY
`
