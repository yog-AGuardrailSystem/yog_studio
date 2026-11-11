import { useEffect, useState } from 'react'
import { diffVersions, restoreVersion, versions, type DiffResult, type VersionSummary } from '../../api/tools'
import { DecisionPill, ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'
import { useAppState } from '../../state'

export default function HistoryPage() {
  const { setApproved } = useAppState()
  const [list, setList] = useState<VersionSummary[] | null>(null)
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [diff, setDiff] = useState<DiffResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const load = () => versions().then((l) => { setList(l); if (!a && l[1]) setA(l[1].id); if (!b && l[0]) setB(l[0].id) }).catch((e) => setError(msg(e)))
  useEffect(() => { void load() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [])

  async function compare() {
    setError(null)
    try { setDiff(await diffVersions(a, b)) } catch (e) { setDiff(null); setError(msg(e)) }
  }
  async function restore(id: string) {
    if (!window.confirm(`Save ${id} as a new approved version? Nothing is overwritten; it becomes the latest.`)) return
    setError(null)
    try {
      const rec = await restoreVersion(id, '')
      setApproved(rec)
      setDone(rec.id)
      await load()
    } catch (e) { setError(msg(e)) }
  }

  if (list && list.length === 0) {
    return (
      <ToolPage id="history">
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center" data-testid="history-empty">
          <p className="font-display text-lg font-bold">No approved versions yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">Every time you approve a policy it is saved here as a version. Approve one on the Review page and it will appear.</p>
        </div>
      </ToolPage>
    )
  }
  return (
    <ToolPage id="history">
      <ErrorBox error={error} />
      {done && <p className="rounded border border-green-300 bg-green-50 p-2 text-sm text-green-800" role="status" data-testid="history-restored">Saved as a new version: {done}</p>}
      <ol className="space-y-2" data-testid="version-list">
        {(list ?? []).map((v) => (
          <li key={v.id} className="flex flex-wrap items-center gap-3 rounded border border-slate-200 bg-white p-3 text-sm">
            <span className="font-mono text-xs">{v.id}</span>
            {v.latest && <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs font-bold text-green-800">latest</span>}
            {v.restored_from && <span className="text-xs text-slate-500">restored from {v.restored_from}</span>}
            <span className="text-xs text-slate-600">{new Date(v.approved_at).toLocaleString()} · {v.clauses} rules · {v.rules} English rule{v.rules === 1 ? '' : 's'}{v.pass_pct != null ? ` · ${v.pass_pct}% pass` : ''}</span>
            {v.note && <span className="italic">“{v.note}”</span>}
            {!v.latest && <button type="button" className="ml-auto text-link underline" onClick={() => void restore(v.id)}>Restore this version</button>}
          </li>
        ))}
      </ol>
      {(list?.length ?? 0) >= 2 && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3 rounded border border-slate-200 bg-white p-3 text-sm">
            <label>From <select value={a} onChange={(e) => setA(e.target.value)} className="rounded border border-slate-300 px-1" data-testid="diff-a">{list?.map((v) => <option key={v.id} value={v.id}>{v.id}</option>)}</select></label>
            <label>to <select value={b} onChange={(e) => setB(e.target.value)} className="rounded border border-slate-300 px-1" data-testid="diff-b">{list?.map((v) => <option key={v.id} value={v.id}>{v.id}</option>)}</select></label>
            <button type="button" onClick={() => void compare()} disabled={!a || !b} className="rounded bg-sky-700 px-4 py-1.5 font-semibold text-on-accent disabled:opacity-50" data-testid="diff-go">Compare</button>
          </div>
          {diff && (
            <div className="space-y-3" data-testid="diff-result">
              <p className="rounded border border-slate-200 bg-white p-3 text-sm font-semibold" data-testid="diff-summary">{diff.summary}</p>
              <div className="grid gap-3 lg:grid-cols-2">
                <pre className="min-w-0 max-h-96 overflow-auto rounded border border-slate-200 bg-slate-50 p-2 font-mono text-xs" aria-label="Text difference">
                  {diff.text_diff ? diff.text_diff.split('\n').map((l, i) => (
                    <div key={i} className={l.startsWith('+') && !l.startsWith('+++') ? 'bg-green-100 text-green-800' : l.startsWith('-') && !l.startsWith('---') ? 'bg-red-100 text-red-800' : ''}>{l || ' '}</div>
                  )) : 'No text difference.'}
                </pre>
                <div className="min-w-0 max-h-96 overflow-auto rounded border border-slate-200 bg-white">
                  <table className="w-full text-left text-xs" data-testid="flips">
                    <thead className="sticky top-0 bg-slate-100 text-slate-600"><tr><th className="p-2">Request</th><th>Before</th><th>After</th></tr></thead>
                    <tbody>
                      {diff.flips.length === 0 && <tr><td colSpan={3} className="p-3 text-slate-600">None of the {diff.probes} probe requests changed.</td></tr>}
                      {diff.flips.map((f, i) => (
                        <tr key={i} className="border-t border-slate-100"><td className="p-2 font-mono">{f.action}({f.actor}, {f.resource}) {f.context.join(' ')}</td><td><DecisionPill d={f.before} /></td><td><DecisionPill d={f.after} /></td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </ToolPage>
  )
}
