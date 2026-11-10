import { useCallback, useEffect, useId, useState } from 'react'
import { getInfo, type Info } from '../api/compile'

/** Real AI / Offline: one switch for the whole app, remembered in this browser, sent with every retrieve/translate call. */
export type AiMode = 'real' | 'offline'
const MODE_KEY = 'yog.aiMode'
const RERANK_KEY = 'yog.rerank'
const EVENT = 'yog-ai-mode'

function read(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function write(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* preference only */ }
  window.dispatchEvent(new Event(EVENT))
}

let infoPromise: Promise<Info | null> | null = null
const loadInfo = () => (infoPromise ??= getInfo().catch(() => { infoPromise = null; return null }))

export interface AiModeState {
  info: Info | null
  mode: AiMode                 // what will actually be used
  setMode: (m: AiMode) => void
  liveReady: boolean           // the server can run the real AI right now
  reason: string | null        // why not, when it cannot
  rerank: boolean              // optional reranker (only ever true in real mode)
  setRerank: (on: boolean) => void
}

export function useAiMode(): AiModeState {
  const [info, setInfo] = useState<Info | null>(null)
  const [, bump] = useState(0)
  useEffect(() => { let on = true; loadInfo().then((i) => { if (on) setInfo(i) }); return () => { on = false } }, [])
  useEffect(() => {
    const h = () => bump((n) => n + 1)
    window.addEventListener(EVENT, h)
    return () => window.removeEventListener(EVENT, h)
  }, [])

  const liveReady = !!info?.live_ready
  const stored = read(MODE_KEY)
  const wanted: AiMode = stored === 'real' || stored === 'offline' ? stored : (info?.default_mode ?? 'offline')
  const mode: AiMode = wanted === 'real' && liveReady ? 'real' : 'offline'
  const setMode = useCallback((m: AiMode) => write(MODE_KEY, m), [])
  const setRerank = useCallback((on: boolean) => write(RERANK_KEY, on ? 'on' : 'off'), [])
  return {
    info, mode, setMode, liveReady, reason: info && !info.live_ready ? info.live_reason : null,
    rerank: mode === 'real' && read(RERANK_KEY) === 'on', setRerank,
  }
}

/** The switch. `compact` is the header version; the full one explains itself. */
export function AiModeToggle({ compact = false }: { compact?: boolean }) {
  const { mode, setMode, liveReady, reason, info } = useAiMode()
  const real = mode === 'real'
  const labelId = useId()
  return (
    <div className="inline-flex items-center gap-2" data-testid="ai-mode">
      <span className="text-sm" id={labelId}>{compact ? 'AI' : 'Drafting mode'}</span>
      <button type="button" role="switch" aria-checked={real} aria-labelledby={labelId} data-testid="ai-mode-toggle"
        disabled={!liveReady && !real && !info} onClick={() => { if (liveReady || real) setMode(real ? 'offline' : 'real') }}
        title={liveReady ? (real ? 'Real AI drafts your rules. Click for Offline.' : 'Offline copies the nearest example. Click for the real AI.') : (reason ?? 'Checking the server…')}
        className={`relative h-6 w-11 rounded-full border border-slate-400 transition-colors ${real ? 'bg-emerald-700' : 'bg-slate-300'} ${liveReady || real ? '' : 'cursor-not-allowed opacity-60'}`}>
        <span aria-hidden className={`absolute top-0.5 h-4.5 w-4.5 rounded-full bg-white shadow transition-all ${real ? 'left-[22px]' : 'left-0.5'}`} style={{ height: 18, width: 18 }} />
      </button>
      <span className="text-sm font-semibold" data-testid="ai-mode-label">{real ? 'Real AI' : 'Offline'}</span>
      {!compact && !liveReady && info && <span className="text-xs text-slate-600" data-testid="ai-mode-reason">({reason})</span>}
    </div>
  )
}
