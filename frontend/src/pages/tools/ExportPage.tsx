import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { exportPack, exportPreview } from '../../api/tools'
import { PolicyPicker, usePolicyChoice } from '../../components/tool/PolicyPicker'
import { ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'
import { useAppState } from '../../state'

export default function ExportPage() {
  const { analysis, tools } = useAppState()
  const { choice, setChoice, policies, ready } = usePolicyChoice()
  const [withAgent, setWithAgent] = useState(!!analysis)
  const [files, setFiles] = useState<string[]>([])
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const pid = choice.ref.policy_id ?? ''
  const agent = withAgent && analysis ? analysis : null
  useEffect(() => {
    setDone(false)
    if (!choice.approved || !pid) { setFiles([]); setReason('Pick an approved policy: the demo and pasted policies were not approved by you.'); return }
    exportPreview(pid, agent?.source ?? null, agent?.filename ?? 'agent.py')
      .then((p) => { setFiles(p.files); setReason(p.ok ? '' : p.reason) })
      .catch((e) => setReason(msg(e)))
  }, [pid, choice.approved, agent?.source, agent?.filename])

  async function download() {
    setBusy(true)
    setError(null)
    try {
      const blob = await exportPack(pid, agent?.source ?? null, agent?.filename ?? 'agent.py', agent ? tools.map((t) => t.name) : [])
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `yog_export_${pid}.zip`
      a.click()
      URL.revokeObjectURL(url)
      setDone(true)
    } catch (e) { setError(msg(e)) } finally { setBusy(false) }
  }

  if (ready && policies.length === 0) {
    return (
      <ToolPage id="export">
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center" data-testid="export-empty">
          <p className="font-display text-lg font-bold">Nothing approved to export yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">An export pack is built from a policy you approved. Write rules, review the draft, and approve it first.</p>
          <Link to="/rules" className="btn-primary mt-4">Write rules</Link>
        </div>
      </ToolPage>
    )
  }
  return (
    <ToolPage id="export">
      <PolicyPicker choice={choice} onChange={setChoice} policies={policies} approvedOnly />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={withAgent} disabled={!analysis} onChange={(e) => setWithAgent(e.target.checked)} data-testid="export-agent" />
        Include my patched agent{analysis ? ` (${analysis.filename})` : ' (upload an agent first to enable this)'}
      </label>
      <section className="rounded border border-slate-200 bg-white p-3 text-sm">
        <h2 className="font-semibold">What will be in the zip</h2>
        {reason ? <p className="mt-1 text-amber-800" data-testid="export-reason">{reason}</p> : (
          <ul className="mt-1 list-disc space-y-0.5 pl-5 font-mono text-xs" data-testid="export-files">{files.map((f) => <li key={f}>{f}</li>)}</ul>
        )}
        <p className="mt-2 text-xs text-slate-600"><code>manifest.json</code> lists the SHA-256 of every file. The pack holds no keys and nothing from other visitors.</p>
        <button type="button" disabled={busy || !!reason || files.length === 0} onClick={() => void download()} className="mt-2 rounded bg-sky-700 px-4 py-1.5 font-semibold text-on-accent disabled:opacity-50" data-testid="export-go">{busy ? 'Building…' : 'Download the pack'}</button>
        {done && <span className="ml-3 text-green-800" role="status" data-testid="export-done">Downloaded.</span>}
      </section>
      <ErrorBox error={error} />
    </ToolPage>
  )
}
