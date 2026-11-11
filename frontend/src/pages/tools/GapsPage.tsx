import { useEffect, useState } from 'react'
import { gaps, type GapReport } from '../../api/tools'
import { PolicyPicker, usePolicyChoice } from '../../components/tool/PolicyPicker'
import { ErrorBox, msg, PolicyLines, ToolPage } from '../../components/tool/ToolPage'
import { loadScenarios } from '../../lib/myScenarios'
import { useAppState } from '../../state'

function Ring({ pct, label }: { pct: number | null; label: string }) {
  const r = 34, c = 2 * Math.PI * r
  const v = pct ?? 0
  return (
    <div className="flex flex-col items-center" data-testid="coverage-ring">
      <svg width="88" height="88" viewBox="0 0 88 88" role="img" aria-label={`${label}: ${pct === null ? 'not measured' : pct + ' percent'}`}>
        <circle cx="44" cy="44" r={r} fill="none" stroke="currentColor" strokeOpacity=".15" strokeWidth="9" />
        <circle cx="44" cy="44" r={r} fill="none" stroke={v >= 100 ? '#16a34a' : '#d97706'} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={`${(c * v) / 100} ${c}`} transform="rotate(-90 44 44)" />
        <text x="44" y="49" textAnchor="middle" fontSize="16" fontWeight="700" fill="currentColor">{pct === null ? 'n/a' : `${pct}%`}</text>
      </svg>
      <span className="mt-1 text-xs text-slate-600">{label}</span>
    </div>
  )
}

export default function GapsPage() {
  const { tools } = useAppState()
  const { choice, setChoice, policies } = usePolicyChoice()
  const [toolText, setToolText] = useState(tools.map((t) => t.name).join(', '))
  const [useMine, setUseMine] = useState(false)
  const [out, setOut] = useState<GapReport | null>(null)
  const [marks, setMarks] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const mine = loadScenarios()

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const names = toolText.split(/[,\n]/).map((x) => x.trim()).filter(Boolean)
      setOut(await gaps(choice.ref, names, useMine ? mine : []))
      setMarks([])
    } catch (e) {
      setOut(null)
      setError(msg(e))
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => { void run() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [choice])

  const proved = out?.findings.filter((f) => f.certainty === 'proved' && f.severity === 'warning').length ?? 0
  return (
    <ToolPage id="gaps">
      <PolicyPicker choice={choice} onChange={setChoice} policies={policies} />
      <div className="grid gap-3 rounded border border-slate-200 bg-white p-3 text-sm md:grid-cols-[1fr_auto]">
        <label className="block">The agent’s tools, comma separated (filled from your uploaded agent)
          <input value={toolText} onChange={(e) => setToolText(e.target.value)} placeholder="unlock_door, set_thermostat" className="mt-1 w-full rounded border border-slate-300 px-2 py-1" data-testid="gaps-tools" />
        </label>
        <div className="flex items-end gap-3">
          <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={useMine} disabled={mine.length === 0} onChange={(e) => setUseMine(e.target.checked)} />
            use my {mine.length} saved scenarios for coverage</label>
          <button type="button" onClick={() => void run()} disabled={busy} className="rounded bg-sky-700 px-4 py-1.5 font-semibold text-on-accent disabled:opacity-50" data-testid="gaps-run">{busy ? 'Working…' : 'Analyze'}</button>
        </div>
      </div>
      <ErrorBox error={error} />
      {out && (
        <div className="space-y-4" data-testid="gaps-result">
          <div className="flex flex-wrap items-center gap-8 rounded-xl border border-slate-200 bg-white p-4">
            <Ring pct={out.coverage_pct} label={out.coverage_pct === null ? 'tools covered (add tools)' : `tools covered (${out.governed}/${out.total})`} />
            <Ring pct={out.clause_coverage_pct} label={`rules exercised (${out.probes} probes)`} />
            <div className="text-sm"><b data-testid="gaps-proved">{proved}</b> proved problem{proved === 1 ? '' : 's'}<br /><b>{out.findings.length}</b> findings in all</div>
          </div>
          {out.findings.length === 0 && <p className="rounded border border-green-300 bg-green-50 p-3 text-sm text-green-800">No findings. That is not a proof the policy is right; it means these checks found nothing.</p>}
          <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
            <ul className="min-w-0 space-y-2" data-testid="gaps-findings">
              {out.findings.map((f, i) => (
                <li key={i} className="rounded border border-slate-200 bg-white p-3 text-sm" data-finding={f.id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-bold ${f.severity === 'warning' ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-800'}`}>{f.severity === 'warning' ? 'Problem' : 'Note'}</span>
                    <span className={`rounded border px-1.5 py-0.5 text-xs ${f.certainty === 'proved' ? 'border-green-600 text-green-800' : 'border-slate-400 text-slate-700'}`}>{f.certainty}</span>
                    <b>{f.title}</b>
                  </div>
                  <p className="mt-1 text-slate-700">{f.detail}</p>
                  {f.lines.length > 0 && <button type="button" className="mt-1 text-xs text-link underline" onClick={() => setMarks(f.lines)}>Show line{f.lines.length > 1 ? 's' : ''} {f.lines.join(', ')}</button>}
                </li>
              ))}
            </ul>
            <div className="min-w-0">
              {out.source && <PolicyLines source={out.source} marks={marks} onLine={(n) => setMarks([n])} />}
              <table className="mt-3 w-full text-left text-xs" data-testid="gaps-clauses">
                <thead className="text-slate-500"><tr><th>Rule</th><th>Fired</th><th>Applied</th></tr></thead>
                <tbody>
                  {out.clauses.map((c) => (
                    <tr key={c.line} className={c.matched === 0 ? 'text-amber-800' : ''}><td>{c.kind} {c.head} (line {c.line})</td><td>{c.matched}×</td><td>{c.tried}×</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </ToolPage>
  )
}
