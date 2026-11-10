import { useState } from 'react'
import { replay, replaySample, type ReplayResult } from '../../api/tools'
import { PolicyPicker, usePolicyChoice } from '../../components/tool/PolicyPicker'
import { DecisionPill, ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'

export default function ReplayPage() {
  const a = usePolicyChoice()
  const b = usePolicyChoice(a.choice)
  const [compare, setCompare] = useState(false)
  const [text, setText] = useState('')
  const [format, setFormat] = useState<'jsonl' | 'csv'>('jsonl')
  const [out, setOut] = useState<ReplayResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function go(fmt: 'jsonl' | 'csv' | 'audit') {
    setBusy(true)
    setError(null)
    try {
      setOut(await replay(a.choice.ref, compare ? b.choice.ref : null, fmt === 'audit' ? '' : text, fmt))
    } catch (e) {
      setOut(null)
      setError(msg(e))
    } finally { setBusy(false) }
  }
  return (
    <ToolPage id="replay">
      <PolicyPicker choice={a.choice} onChange={a.setChoice} policies={a.policies} label="Policy" />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} data-testid="replay-compare" /> Compare with a second policy (for example an older version)</label>
      {compare && <PolicyPicker choice={b.choice} onChange={b.setChoice} policies={b.policies} label="Second policy" />}
      <section className="rounded border border-slate-200 bg-white p-3 text-sm">
        <div className="flex flex-wrap items-center gap-3">
          <b>The calls to replay</b>
          <select value={format} onChange={(e) => setFormat(e.target.value as 'jsonl' | 'csv')} className="rounded border border-slate-300 px-1" aria-label="Format" data-testid="replay-format"><option value="jsonl">JSON lines</option><option value="csv">CSV</option></select>
          <button type="button" className="text-link underline" onClick={async () => { try { const s = await replaySample(); setText(s.text); setFormat('jsonl') } catch (e) { setError(msg(e)) } }} data-testid="replay-sample">Load a sample day</button>
          <button type="button" className="text-link underline" onClick={() => void go('audit')} data-testid="replay-audit">Replay my audit log instead</button>
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} spellCheck={false} aria-label="Calls to replay"
          placeholder={format === 'jsonl' ? '{"tool": "unlock_door", "args": {"door_id": "front_door"}, "hour": 3, "day": "tue"}' : 'tool,hour,day,args\nunlock_door,3,tue,"{""door_id"": ""front_door""}"'}
          className="mt-2 w-full rounded border border-slate-300 p-2 font-mono text-xs" data-testid="replay-text" />
        <p className="text-xs text-slate-500">Up to 500 calls. Each needs a tool name; args, hour (0-23), day and actor are optional. Nothing here is executed.</p>
        <button type="button" disabled={busy || !text.trim()} onClick={() => void go(format)} className="mt-2 rounded bg-sky-700 px-4 py-1.5 font-semibold text-on-accent disabled:opacity-50" data-testid="replay-run">{busy ? 'Replaying…' : 'Replay'}</button>
      </section>
      <ErrorBox error={error} />
      {out && (
        <div className="space-y-3" data-testid="replay-result">
          <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm" data-testid="replay-summary">
            <b>{out.summary.denied}</b> of {out.summary.total} calls would be blocked, <b>{out.summary.allowed}</b> allowed ({out.policy_label}).
            {out.other_label && <> The second policy ({out.other_label}) allows <b>{out.summary.other_allowed}</b>; <b className={out.summary.changed ? 'text-amber-800' : ''} data-testid="replay-changed">{out.summary.changed}</b> call{out.summary.changed === 1 ? '' : 's'} get a different answer.</>}
            {out.problems.length > 0 && <ul className="mt-2 list-disc pl-5 text-xs text-amber-800">{out.problems.map((p) => <li key={p}>{p}</li>)}</ul>}
          </div>
          <div className="max-h-[30rem] overflow-auto rounded border border-slate-200 bg-white">
            <table className="w-full text-left text-xs" data-testid="replay-table">
              <thead className="sticky top-0 bg-slate-100 text-slate-600"><tr><th className="p-2">#</th><th>When</th><th>Call</th><th>Decision</th>{out.other_label && <th>Second policy</th>}<th>Reason</th></tr></thead>
              <tbody>
                {out.rows.map((r) => (
                  <tr key={r.n} className={`border-t border-slate-100 align-top ${r.changed ? 'bg-amber-50 text-amber-900' : ''}`} data-changed={r.changed}>
                    <td className="p-2">{r.n}</td><td>{r.day} {String(r.hour).padStart(2, '0')}:00</td>
                    <td className="font-mono">{r.tool}({Object.values(r.args).join(', ')})</td>
                    <td><DecisionPill d={r.decision} /></td>
                    {out.other_label && <td>{r.other && <DecisionPill d={r.other} />}{r.changed && <span className="ml-1 font-bold">changed</span>}</td>}
                    <td>{r.reason}</td>
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
