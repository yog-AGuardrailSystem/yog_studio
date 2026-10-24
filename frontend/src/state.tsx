import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { AnalyzeResponse, PolicyDraft, PolicyRecord, Tool } from './api/types'

// App-wide state that has to survive page navigation. Mirrored to sessionStorage so a refresh keeps the demo state.
interface AppState {
  analysis: AnalyzeResponse | null
  setAnalysis: (a: AnalyzeResponse | null) => void
  /** Tools the policy will be written against: detected tools, or the hand-picked candidates. */
  tools: Tool[]
  setTools: (t: Tool[]) => void
  /** The English rules the user has typed. */
  rules: string[]
  setRules: (r: string[]) => void
  /** Latest generated draft (not live until a human approves it on the Review page). */
  draft: PolicyDraft | null
  setDraft: (d: PolicyDraft | null) => void
  /** The policy a human approved: the only one later screens may treat as live. */
  approved: PolicyRecord | null
  setApproved: (p: PolicyRecord | null) => void
}

const Ctx = createContext<AppState | null>(null)

function load<T>(key: string, fallback: T): T {
  try {
    const raw = sessionStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function usePersisted<T>(key: string, initial: T) {
  const [v, setV] = useState<T>(() => load(key, initial))
  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(v))
    } catch {
      /* storage unavailable: ignore */
    }
  }, [key, v])
  return [v, setV] as const
}

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [analysis, setAnalysis] = usePersisted<AnalyzeResponse | null>('yog.analysis', null)
  const [tools, setTools] = usePersisted<Tool[]>('yog.tools', [])
  const [rules, setRules] = usePersisted<string[]>('yog.rules', [''])
  const [draft, setDraft] = usePersisted<PolicyDraft | null>('yog.draft', null)
  const [approved, setApproved] = usePersisted<PolicyRecord | null>('yog.approved', null)
  return (
    <Ctx.Provider value={{ analysis, setAnalysis, tools, setTools, rules, setRules, draft, setDraft, approved, setApproved }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAppState(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAppState outside AppStateProvider')
  return v
}
