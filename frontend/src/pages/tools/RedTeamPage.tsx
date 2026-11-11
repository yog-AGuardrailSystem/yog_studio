import { useEffect, useState } from 'react'
import { mapSuggest, redTeam, type Attack, type Invariant, type MapSuggest, type RedTeamReport } from '../../api/tools'
import { PolicyPicker, usePolicyChoice } from '../../components/tool/PolicyPicker'
import { DecisionPill, ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'
import { addScenario, loadScenarios } from '../../lib/myScenarios'

const num = (v: string): number | null => (v.trim() === '' || Number.isNaN(Number(v)) ? null : Math.trunc(Number(v)))

export default function RedTeamPage() {
  const { choice, setChoice, policies } = usePolicyChoice()
  const [sug, setSug] = useState<MapSuggest | null>(null)
  const [invs, setInvs] = useState<Invariant[]>([])
  const [out, setOut] = useState<RedTeamReport | null>(null)
  const [show, setShow] = useState<'findings' | 'allowed'>('findings')
  const [saved, setSaved] = useState(loadScenarios().length)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    mapSuggest(choice.ref).then((s) => { setSug(s); setInvs([]); setOut(null) }).catch((e) => setError(msg(e)))
  }, [choice])

  const patch = (i: number, p: Partial<Invariant>) => setInvs((l) => l.map((x, k) => (k === i ? { ...x, ...p } : x)))
  function addExample() {
    if (!sug) return
    const a = sug.actions[0] ?? ''
    setInvs((l) => [...l, sug.uses_hour ? { action: a, must: 'DENY', hour_min: 23, hour_max: 5 } : { action: a, must: 'DENY' }])
  }
  async function run() {
    setBusy(true)
    setError(null)
    try {
      setOut(await redTeam(choice.ref, invs.filter((x) => x.action)))
    } catch (e) {
      setOut(null)
      setError(msg(e))
    } finally {
      setBusy(false)
    }
  }
  function keep(a: Attack, expected: 'ALLOW' | 'DENY') {
    setSaved(addScenario({ actor: a.actor, action: a.action, resource: a.resource, context: a.context, expected }).length)
  }

  const rows = (out?.attacks ?? []).filter((a) => (show === 'findings' ? a.violates !== null || a.suspicious : true))
  return (
    <ToolPage id="redteam">
      <PolicyPicker choice={choice} onChange={setChoice} policies={policies} />
      <section className="rounded border border-slate-200 bg-white p-3 text-sm" aria-labelledby="inv-h">
        <h2 id="inv-h" className="font-semibold">What must always hold</h2>
        <p className="text-xs text-slate-600">Each line is a promise about the policy. Red-Team looks for a request that breaks it. Leave this empty to just list ALLOWs that look unexpected.</p>
        <ul className="mt-2 space-y-2">
          {invs.map((v, i) => {
            const argKey = v.arg ? `${v.arg.tool}.${v.arg.param}` : ''
            return (
              <li key={i} className="flex flex-wrap items-center gap-2 rounded border border-slate-200 p-2" data-testid="invariant">
                <select aria-label="Action" value={v.action} onChange={(e) => patch(i, { action: e.target.value })} className="rounded border border-slate-300 px-1 py-0.5">
                  {sug?.actions.map((a) => <option key={a}>{a}</option>)}
                </select>
                <span>must be</span>
                <select aria-label="Must be" value={v.must} onChange={(e) => patch(i, { must: e.target.value as 'ALLOW' | 'DENY' })} className="rounded border border-slate-300 px-1 py-0.5"><option>DENY</option><option>ALLOW</option></select>
                <span>when hour is</span>
                <input aria-label="Hour from" type="number" min={0} max={23} value={v.hour_min ?? ''} onChange={(e) => patch(i, { hour_min: num(e.target.value) })} className="w-14 rounded border border-slate-300 px-1" />
                <span>to</span>
                <input aria-label="Hour to" type="number" min={0} max={23} value={v.hour_max ?? ''} onChange={(e) => patch(i, { hour_max: num(e.target.value) })} className="w-14 rounded border border-slate-300 px-1" />
                {(sug?.arg_keys.length ?? 0) > 0 && (
                  <>
                    <span>and</span>
                    <select aria-label="Argument" value={argKey} onChange={(e) => { const k = sug?.arg_keys.find((x) => `${x.tool}.${x.param}` === e.target.value); patch(i, { arg: k ? { tool: k.tool, param: k.param, min: null, max: null } : null }) }} className="rounded border border-slate-300 px-1 py-0.5">
                      <option value="">(no argument condition)</option>
                      {sug?.arg_keys.map((k) => <option key={`${k.tool}.${k.param}`} value={`${k.tool}.${k.param}`}>{k.tool}.{k.param}</option>)}
                    </select>
                    {v.arg && (<>
                      <span>from</span><input aria-label="Argument min" type="number" value={v.arg.min ?? ''} onChange={(e) => patch(i, { arg: { ...v.arg!, min: num(e.target.value) } })} className="w-16 rounded border border-slate-300 px-1" />
                      <span>to</span><input aria-label="Argument max" type="number" value={v.arg.max ?? ''} onChange={(e) => patch(i, { arg: { ...v.arg!, max: num(e.target.value) } })} className="w-16 rounded border border-slate-300 px-1" />
                    </>)}
                  </>
                )}
                <button type="button" className="ml-auto text-xs text-red-800 underline" onClick={() => setInvs((l) => l.filter((_, k) => k !== i))}>Remove</button>
              </li>
            )
          })}
        </ul>
        <div className="mt-2 flex gap-2">
          <button type="button" className="rounded border border-slate-300 px-3 py-1" onClick={addExample} disabled={!sug?.actions.length} data-testid="add-invariant">Add a promise</button>
          <button type="button" onClick={() => void run()} disabled={busy} className="rounded bg-sky-700 px-4 py-1.5 font-semibold text-on-accent disabled:opacity-50" data-testid="redteam-run">{busy ? 'Attacking…' : 'Run Red-Team'}</button>
        </div>
      </section>
      <ErrorBox error={error} />
      {out && (
        <div className="space-y-3" data-testid="redteam-result">
          <div className="flex flex-wrap items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 text-sm">
            <div><b className={out.counterexamples ? 'text-red-800' : 'text-green-800'} data-testid="rt-cx">{out.counterexamples}</b> promise{out.counterexamples === 1 ? '' : 's'} broken</div>
            <div><b data-testid="rt-sus">{out.suspicious}</b> ALLOWs to look at</div>
            <div><b>{out.checked}</b> requests tried</div>
            <p className="basis-full text-xs text-slate-600">{out.note}</p>
          </div>
          <table className="w-full text-left text-xs" data-testid="rt-families">
            <thead className="text-slate-500"><tr><th>Kind of attack</th><th>Tried</th><th>Allowed</th></tr></thead>
            <tbody>{out.families.map((f) => <tr key={f.family}><td>{f.family.replace('_', ' ')}</td><td>{f.total}</td><td>{f.allowed}</td></tr>)}</tbody>
          </table>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label>Show <select value={show} onChange={(e) => setShow(e.target.value as 'findings' | 'allowed')} className="rounded border border-slate-300 px-1"><option value="findings">broken promises and suspicious ALLOWs</option><option value="allowed">every ALLOW</option></select></label>
            <span className="text-xs text-slate-500">{saved} scenarios saved in this browser (used by Gap Analyzer and Test Strength)</span>
          </div>
          <div className="max-h-[28rem] overflow-auto rounded border border-slate-200 bg-white">
            <table className="w-full text-left text-xs" data-testid="rt-attacks">
              <thead className="sticky top-0 bg-slate-100 text-slate-600"><tr><th className="p-2">Result</th><th>Attack</th><th>Request</th><th>Why</th><th /></tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={5} className="p-3 text-slate-600">Nothing to show here. That is not a proof the policy is safe.</td></tr>}
                {rows.map((a, i) => (
                  <tr key={i} className="border-t border-slate-100 align-top">
                    <td className="p-2"><DecisionPill d={a.decision} />{a.violates !== null && <div className="mt-1 font-bold text-red-800">breaks promise {a.violates + 1}</div>}{a.suspicious && a.violates === null && <div className="mt-1 text-amber-800">look at this</div>}</td>
                    <td>{a.family.replace('_', ' ')}: {a.note}</td>
                    <td className="font-mono">{a.action}({a.actor}, {a.resource}) {a.context.join(' ')}</td>
                    <td>{a.reason}</td>
                    <td className="p-2"><button type="button" className="text-link underline" onClick={() => keep(a, 'DENY')}>Keep as a test: must be DENY</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </ToolPage>
  )
}
