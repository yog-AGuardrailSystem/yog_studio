import { useEffect, useState } from 'react'
import { listPolicies } from '../../api/policies'
import type { PolicyRef } from '../../api/tools'
import type { PolicyRecord } from '../../api/types'

export interface PolicyChoice {
  ref: PolicyRef
  label: string
  approved: boolean
}

const DEMO: PolicyChoice = { ref: { policy_id: 'demo' }, label: 'Demo policy (hand-written)', approved: false }

/** The policy a tool works on. Starts with the visitor's latest approved policy, or the demo when there is none. */
export function usePolicyChoice(initial?: PolicyChoice) {
  const [choice, setChoice] = useState<PolicyChoice>(initial ?? DEMO)
  const [policies, setPolicies] = useState<PolicyRecord[]>([])
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let alive = true
    listPolicies()
      .then((p) => {
        if (!alive) return
        setPolicies(p)
        if (!initial && p.length) setChoice({ ref: { policy_id: p[0].id }, label: `Approved ${p[0].id}`, approved: true })
      })
      .catch(() => undefined)
      .finally(() => alive && setReady(true))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return { choice, setChoice, policies, ready }
}

export function PolicyPicker({ choice, onChange, policies, label = 'Policy', allowPaste = true, approvedOnly = false }: {
  choice: PolicyChoice
  onChange: (c: PolicyChoice) => void
  policies: PolicyRecord[]
  label?: string
  allowPaste?: boolean
  approvedOnly?: boolean
}) {
  const [pasting, setPasting] = useState(false)
  const [text, setText] = useState('')
  const current = choice.ref.source ? 'paste' : (choice.ref.policy_id ?? 'demo')

  function pick(v: string) {
    if (v === 'demo') { setPasting(false); onChange(DEMO) }
    else if (v === 'paste') setPasting(true)
    else {
      setPasting(false)
      const p = policies.find((x) => x.id === v)
      onChange({ ref: { policy_id: v }, label: `Approved ${v}${p?.approved_at ? '' : ''}`, approved: true })
    }
  }

  return (
    <div className="rounded border border-slate-200 bg-white p-3 text-sm" data-testid="policy-picker">
      <label className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{label}</span>
        <select value={pasting ? 'paste' : current} onChange={(e) => pick(e.target.value)} className="min-w-0 max-w-full rounded border border-slate-300 px-2 py-1" data-testid="policy-select">
          {policies.map((p, i) => (
            <option key={p.id} value={p.id}>{i === 0 ? 'Latest approved: ' : 'Approved: '}{p.id}{p.note ? ` (${p.note})` : ''}</option>
          ))}
          {!approvedOnly && <option value="demo">Demo policy (hand-written)</option>}
          {allowPaste && !approvedOnly && <option value="paste">Paste my own…</option>}
        </select>
        <span className="text-xs text-slate-500">{choice.approved ? 'approved by you' : approvedOnly ? '' : 'not an approved policy: fine for exploring, not for shipping'}</span>
      </label>
      {pasting && (
        <div className="mt-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} spellCheck={false} aria-label="Paste a YOG policy"
            className="w-full rounded border border-slate-300 p-2 font-mono text-xs" placeholder="fact role(agent, assistant)&#10;allow can_unlock_door(Actor, Door):&#10;    role(Actor, assistant)" data-testid="policy-paste" />
          <button type="button" disabled={!text.trim()} onClick={() => onChange({ ref: { source: text }, label: 'Pasted policy', approved: false })}
            className="mt-1 rounded bg-sky-700 px-3 py-1 text-xs font-semibold text-on-accent disabled:opacity-50" data-testid="policy-use-paste">Use this policy</button>
        </div>
      )}
    </div>
  )
}
