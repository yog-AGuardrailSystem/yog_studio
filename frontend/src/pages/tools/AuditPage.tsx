import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AUDIT_CSV_URL, auditList, auditVerify, type AuditEntry } from '../../api/tools'
import { DecisionPill, ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEntry[]>([])
  const [total, setTotal] = useState(0)
  const [decision, setDecision] = useState('')
  const [tool, setTool] = useState('')
  const [q, setQ] = useState('')
  const [verify, setVerify] = useState<{ ok: boolean; checked: number; problem: string } | null>(null)
  const [pos, setPos] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await auditList({ decision, tool, q, limit: 1000 })
      setRows(r.entries)
      setTotal(r.total)
      setPos(null)
      setError(null)
    } catch (e) { setError(msg(e)) } finally { setLoaded(true) }
  }, [decision, tool, q])
  useEffect(() => { void load() }, [load])

  const tools = useMemo(() => [...new Set(rows.map((r) => r.tool))].sort(), [rows])
  const oldestFirst = useMemo(() => [...rows].reverse(), [rows])
  const shown = pos === null ? rows : oldestFirst.slice(0, pos).reverse()
  const allow = shown.filter((r) => r.decision === 'ALLOW').length
  const deny = shown.filter((r) => r.decision === 'DENY').length

  return (
    <ToolPage id="audit">
      <div className="flex flex-wrap items-center gap-3 rounded border border-slate-200 bg-white p-3 text-sm">
        <label>Decision <select value={decision} onChange={(e) => setDecision(e.target.value)} className="ml-1 rounded border border-slate-300 px-1" data-testid="audit-decision">
          <option value="">all</option><option>ALLOW</option><option>DENY</option><option>UNGUARDED</option></select></label>
        <label>Tool <select value={tool} onChange={(e) => setTool(e.target.value)} className="ml-1 rounded border border-slate-300 px-1" data-testid="audit-tool">
          <option value="">all</option>{tools.map((t) => <option key={t}>{t}</option>)}</select></label>
        <label>Search <input value={q} onChange={(e) => setQ(e.target.value)} className="ml-1 rounded border border-slate-300 px-2 py-0.5" data-testid="audit-q" /></label>
        <button type="button" className="rounded border border-slate-300 px-3 py-1" onClick={async () => { try { setVerify(await auditVerify()) } catch (e) { setError(msg(e)) } }} data-testid="audit-verify">Verify the chain</button>
        <a className="rounded border border-slate-300 px-3 py-1" href={AUDIT_CSV_URL} download data-testid="audit-csv">Export CSV</a>
        <Link to="/studio/replay" className="text-link underline">Replay these against a policy</Link>
      </div>
      <ErrorBox error={error} />
      {verify && (
        <p className={`rounded border p-2 text-sm ${verify.ok ? 'border-green-300 bg-green-50 text-green-800' : 'border-red-300 bg-red-50 text-red-800'}`} role="status" data-testid="audit-verify-result">
          {verify.ok ? `Chain intact: ${verify.checked} entries, each matches the one before it.` : `Chain broken: ${verify.problem}. The log was changed after it was written.`}
        </p>
      )}
      {loaded && total === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center" data-testid="audit-empty">
          <p className="font-display text-lg font-bold">No decisions recorded yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">Every command you send on the device simulator is recorded here with the policy that decided it.</p>
          <Link to="/device" className="btn-primary mt-4">Open the device simulator</Link>
        </div>
      ) : (
        <>
          {oldestFirst.length > 1 && (
            <div className="rounded border border-slate-200 bg-white p-3 text-sm">
              <label className="block">Replay the day: show the first <b data-testid="scrub-n">{pos ?? oldestFirst.length}</b> of {oldestFirst.length} decisions
                <input type="range" min={0} max={oldestFirst.length} value={pos ?? oldestFirst.length} onChange={(e) => setPos(Number(e.target.value))} className="mt-1 block w-full" data-testid="audit-scrub" />
              </label>
              <p className="mt-1 text-xs text-slate-600">{allow} allowed, {deny} denied so far.</p>
            </div>
          )}
          <div className="max-h-[32rem] overflow-auto rounded border border-slate-200 bg-white" data-testid="audit-table">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-100 text-slate-600"><tr><th className="p-2">#</th><th>Sim time</th><th>Command</th><th>Decision</th><th>Reason</th><th>Policy</th><th /></tr></thead>
              <tbody>
                {shown.map((r) => {
                  const qs = new URLSearchParams({ action: "can_" + r.tool, resource: String(Object.values(r.args).find((v) => typeof v === 'string') ?? 'item'), ctx: `hour(now, ${r.sim_hour})` })
                  return (
                    <tr key={r.seq} className="border-t border-slate-100 align-top">
                      <td className="p-2">{r.seq}</td><td>{r.sim_day} {String(r.sim_hour).padStart(2, '0')}:00</td>
                      <td className="font-mono">{r.tool}({Object.values(r.args).join(', ')})</td>
                      <td><DecisionPill d={r.decision} /></td><td>{r.reason}</td>
                      <td className="font-mono">{r.policy_id ? r.policy_id.slice(-8) : '–'}</td>
                      <td><Link className="text-link underline" to={`/studio/why?${qs}`}>Why?</Link></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ToolPage>
  )
}
