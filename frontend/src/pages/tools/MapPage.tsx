import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { mapSuggest, policyMap, type Axis, type MapResult, type MapSuggest } from '../../api/tools'
import { PolicyPicker, usePolicyChoice } from '../../components/tool/PolicyPicker'
import { ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'

type Kind = 'hour' | 'day' | `arg:${string}` | 'none'

function axisFrom(kind: Kind, sug: MapSuggest | null): Axis | null {
  if (kind === 'none') return null
  if (kind === 'hour' || kind === 'day') return { kind }
  const key = sug?.arg_keys.find((k) => `arg:${k.tool}.${k.param}` === kind)
  return key ? { kind: 'arg', tool: key.tool, param: key.param, values: key.values } : null
}

export default function MapPage() {
  const { choice, setChoice, policies } = usePolicyChoice()
  const [sug, setSug] = useState<MapSuggest | null>(null)
  const [action, setAction] = useState('')
  const [actor, setActor] = useState('agent')
  const [resource, setResource] = useState('item')
  const [xk, setXk] = useState<Kind>('hour')
  const [yk, setYk] = useState<Kind>('day')
  const [fixed, setFixed] = useState('')
  const [out, setOut] = useState<MapResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    mapSuggest(choice.ref)
      .then((s) => {
        setSug(s)
        setAction(s.actions[0] ?? '')
        setActor(s.actors[0] ?? 'agent')
        setResource(s.resources[0] ?? 'item')
        const argKey = s.arg_keys[0]
        if (s.uses_hour && argKey) { setXk('hour'); setYk(`arg:${argKey.tool}.${argKey.param}`) }
        else if (s.uses_hour) { setXk('hour'); setYk('day') }
        else if (argKey) { setXk(`arg:${argKey.tool}.${argKey.param}`); setYk('none') }
        else { setXk('hour'); setYk('day') }
        setOut(null)
      })
      .catch((e) => setError(msg(e)))
  }, [choice])

  const fixedFacts = fixed.split('\n').map((x) => x.trim()).filter(Boolean)
  async function run() {
    const x = axisFrom(xk, sug)
    if (!x) { setError('Pick something for the horizontal axis.'); return }
    setBusy(true)
    setError(null)
    try {
      setOut(await policyMap(choice.ref, { actor, action, resource, context: fixedFacts, x, y: axisFrom(yk, sug) }))
    } catch (e) {
      setOut(null)
      setError(msg(e))
    } finally {
      setBusy(false)
    }
  }

  const argOptions = (sug?.arg_keys ?? []).map((k) => ({ v: `arg:${k.tool}.${k.param}` as Kind, t: `${k.tool}.${k.param}` }))
  const axisOptions = (none: boolean) => (
    <>
      {none && <option value="none">(one row)</option>}
      <option value="hour">hour of day</option>
      <option value="day">day of week</option>
      {argOptions.map((o) => <option key={o.v} value={o.v}>{o.t}</option>)}
    </>
  )

  function whyHref(r: number, c: number): string {
    if (!out) return '#'
    const facts = [...fixedFacts]
    for (const [title, label] of [[out.x_title, out.x_labels[c]], [out.y_title, out.y_labels[r]]] as const) {
      if (!label) continue
      if (title === 'hour of day') facts.push(`hour(now, ${Number(label)})`)
      else if (title === 'day of week') facts.push(`day(now, ${label})`)
      else { const [t, p] = title.split('.'); facts.push(`arg(${t}, ${p}, ${label})`) }
    }
    const q = new URLSearchParams({ action, actor, resource, ctx: facts.join('|') })
    return `/studio/why?${q}`
  }

  return (
    <ToolPage id="map">
      <PolicyPicker choice={choice} onChange={setChoice} policies={policies} />
      <form className="grid gap-3 rounded border border-slate-200 bg-white p-3 text-sm md:grid-cols-3" onSubmit={(e) => { e.preventDefault(); void run() }}>
        <label className="block">Action
          <select value={action} onChange={(e) => setAction(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" data-testid="map-action">
            {sug?.actions.map((a) => <option key={a}>{a}</option>)}
          </select>
        </label>
        <label className="block">Actor
          <input value={actor} onChange={(e) => setActor(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" />
        </label>
        <label className="block">Resource
          <input value={resource} onChange={(e) => setResource(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" />
        </label>
        <label className="block">Horizontal axis
          <select value={xk} onChange={(e) => setXk(e.target.value as Kind)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" data-testid="map-x">{axisOptions(false)}</select>
        </label>
        <label className="block">Vertical axis
          <select value={yk} onChange={(e) => setYk(e.target.value as Kind)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" data-testid="map-y">{axisOptions(true)}</select>
        </label>
        <label className="block">Facts held fixed (one per line)
          <textarea value={fixed} onChange={(e) => setFixed(e.target.value)} rows={2} spellCheck={false} placeholder="arg(open_valve, percent, 30)" className="mt-1 w-full rounded border border-slate-300 p-1 font-mono text-xs" />
        </label>
        <div className="md:col-span-3">
          <button type="submit" disabled={busy || !action} className="rounded bg-sky-700 px-4 py-1.5 font-semibold text-on-accent disabled:opacity-50" data-testid="map-run">{busy ? 'Working…' : 'Draw the map'}</button>
        </div>
      </form>
      <ErrorBox error={error} />

      {out && (
        <div className="space-y-2" data-testid="map-result">
          <p className="text-sm" data-testid="map-summary">
            <b>{out.allow}</b> cells allowed, <b>{out.deny}</b> denied. Each cell is one engine decision. <span className="text-slate-500">Click a cell for its proof.</span>
          </p>
          <div className="relative overflow-auto rounded border border-slate-200 bg-white p-2">
            <table className="border-separate border-spacing-0.5 text-center text-xs" aria-label={`Decisions for ${action}`}>
              <thead>
                <tr><th className="text-left font-normal text-slate-500">{out.y_title}{out.y_title ? ' ↓ / ' : ''}{out.x_title} →</th>{out.x_labels.map((l) => <th key={l} className="px-0.5 font-normal text-slate-600">{l}</th>)}</tr>
              </thead>
              <tbody>
                {out.cells.map((row, r) => (
                  <tr key={r}>
                    <th className="pr-2 text-right font-normal text-slate-600">{out.y_labels[r]}</th>
                    {row.map((c, i) => (
                      <td key={i}>
                        <Link to={whyHref(r, i)} title={`${c === 'A' ? 'ALLOW' : 'DENY'}: ${out.reasons[r][i]}`} data-cell={c}
                          className={`flex h-7 min-w-7 items-center justify-center rounded font-bold ${c === 'A' ? 'bg-green-200 text-green-800' : 'bg-red-200 text-red-800'}`}>
                          <span className="sr-only">{c === 'A' ? 'ALLOW' : 'DENY'} at {out.x_labels[i]}{out.y_labels[r] ? `, ${out.y_labels[r]}` : ''}</span>
                          <span aria-hidden>{c}</span>
                        </Link>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-500">A = ALLOW, D = DENY. {out.policy_label}.</p>
        </div>
      )}
    </ToolPage>
  )
}
