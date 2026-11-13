import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { mapSuggest, why, type MapSuggest, type WhyResponse } from '../../api/tools'
import { EngineBadge } from '../../components/EngineBadge'
import { PolicyPicker, usePolicyChoice } from '../../components/tool/PolicyPicker'
import { DecisionPill, ErrorBox, msg, PolicyLines, ToolPage } from '../../components/tool/ToolPage'

const STATUS_TEXT: Record<string, string> = {
  matched: 'matched',
  failed: 'did not match',
  head_mismatch: 'is about a different actor or resource',
  error: 'could not be evaluated',
}

export default function WhyPage() {
  const [params] = useSearchParams()
  const { choice, setChoice, policies } = usePolicyChoice()
  const [sug, setSug] = useState<MapSuggest | null>(null)
  const [actor, setActor] = useState(params.get('actor') ?? 'agent')
  const [action, setAction] = useState(params.get('action') ?? '')
  const [resource, setResource] = useState(params.get('resource') ?? 'item')
  const [ctx, setCtx] = useState((params.get('ctx') ?? '').split('|').filter(Boolean).join('\n'))
  const [out, setOut] = useState<WhyResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const autoRan = useRef(false)

  useEffect(() => {
    mapSuggest(choice.ref)
      .then((s) => {
        setSug(s)
        setAction((a) => a || s.actions[0] || '')
      })
      .catch((e) => setError(msg(e)))
  }, [choice])

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const facts = ctx.split('\n').map((x) => x.trim()).filter(Boolean)
      setOut(await why(choice.ref, actor.trim(), action.trim(), resource.trim(), facts))
    } catch (e) {
      setOut(null)
      setError(msg(e))
    } finally {
      setBusy(false)
    }
  }
  // arriving from the Policy Map or the device log with a request in the address: answer it straight away
  useEffect(() => {
    if (!autoRan.current && params.get('action') && sug) {
      autoRan.current = true
      void run()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sug])

  const r = out?.result
  const marks = r ? r.clauses.filter((c) => c.status === 'matched').map((c) => c.line) : []

  return (
    <ToolPage id="why">
      <PolicyPicker choice={choice} onChange={setChoice} policies={policies} />
      <form className="grid gap-3 rounded border border-slate-200 bg-white p-3 text-sm md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void run() }}>
        <label className="block">Who asks (actor)
          <input list="why-actors" value={actor} onChange={(e) => setActor(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" data-testid="why-actor" />
          <datalist id="why-actors">{sug?.actors.map((a) => <option key={a} value={a} />)}</datalist>
        </label>
        <label className="block">Action
          <select value={action} onChange={(e) => setAction(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" data-testid="why-action">
            {action && !sug?.actions.includes(action) && <option value={action}>{action}</option>}
            {sug?.actions.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
        <label className="block">Resource
          <input value={resource} onChange={(e) => setResource(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" data-testid="why-resource" />
        </label>
        <label className="block md:row-span-2">Facts that come with the request (one per line)
          <textarea value={ctx} onChange={(e) => setCtx(e.target.value)} rows={4} spellCheck={false} placeholder={'hour(now, 3)\narg(set_thermostat, temperature, 30)'}
            className="mt-1 w-full rounded border border-slate-300 p-2 font-mono text-xs" data-testid="why-context" />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          {sug?.uses_hour && (
            <>
              <span className="text-xs text-slate-500">Quick hour:</span>
              {[3, 12, 23].map((h) => (
                <button key={h} type="button" className="rounded border border-slate-300 px-2 py-0.5 text-xs"
                  onClick={() => setCtx((c) => [...c.split('\n').filter((l) => l.trim() && !l.startsWith('hour(')), `hour(now, ${h})`].join('\n'))}>{h}:00</button>
              ))}
            </>
          )}
          <button type="submit" disabled={busy || !action} className="ml-auto rounded bg-sky-700 px-4 py-1.5 font-semibold text-on-accent disabled:opacity-50" data-testid="why-run">
            {busy ? 'Working…' : 'Explain this decision'}
          </button>
        </div>
      </form>
      <ErrorBox error={error} />

      {r && out && (
        <div className="space-y-3" data-testid="why-result">
          <div className={`rounded-xl border p-4 ${r.decision === 'ALLOW' ? 'border-green-300 bg-green-50 text-green-800' : 'border-red-300 bg-red-50 text-red-800'}`} role="status">
            <div className="flex items-center gap-2"><DecisionPill d={r.decision} /><span className="font-display text-lg font-bold" data-testid="why-verdict">{r.verdict}</span></div>
            {!out.consistent && <p className="mt-1 text-sm">The step-by-step explanation did not agree with the engine and is hidden. The engine’s answer above is the one that counts.</p>}
            <p className="mt-1 text-xs opacity-80">Engine reason: {r.reason} <EngineBadge className="ml-1" /></p>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="min-w-0 space-y-2" data-testid="why-clauses">
              {r.clauses.length === 0 && <p className="text-sm text-slate-600">No allow or deny rule is written for this action.</p>}
              {r.clauses.map((c) => (
                <div key={`${c.kind}-${c.line}`} className="rounded border border-slate-200 bg-white p-3 text-sm" data-testid={`clause-${c.line}`} data-status={c.status}>
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-bold ${c.kind === 'deny' ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>{c.kind}</span>
                    <b className="font-mono">{c.head}</b> <span className="text-slate-500">line {c.line}</span>
                    <span className={`ml-auto text-xs font-semibold ${c.status === 'matched' ? 'text-green-800' : 'text-slate-600'}`}>{STATUS_TEXT[c.status]}</span>
                  </div>
                  {c.steps.length > 0 && (
                    <ul className="mt-2 space-y-0.5 font-mono text-xs">
                      {c.steps.map((s, i) => (
                        <li key={i} className={s.ok === false ? 'font-bold text-red-800' : s.ok === null ? 'text-slate-400' : 'text-slate-700'}>
                          <span aria-hidden className="mr-1">{s.ok === true ? '✓' : s.ok === false ? '✗' : '·'}</span>
                          <span className="sr-only">{s.ok === true ? 'held: ' : s.ok === false ? 'failed here: ' : 'not reached: '}</span>
                          {s.text}{s.note ? <span className="ml-2 font-sans font-normal">({s.note})</span> : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
            <div className="min-w-0">
              <p className="mb-1 text-xs text-slate-500">{out.policy_label}. Highlighted: the rule(s) that matched.</p>
              <PolicyLines source={out.source} marks={marks} />
              {r.context.length > 0 && <p className="mt-2 text-xs text-slate-600">Facts used: <span className="font-mono">{r.context.join(', ')}</span></p>}
            </div>
          </div>
        </div>
      )}
    </ToolPage>
  )
}
