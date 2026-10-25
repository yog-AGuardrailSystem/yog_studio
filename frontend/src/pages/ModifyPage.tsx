import { DiffEditor } from '@monaco-editor/react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadBundle, modify, type ModifyResult } from '../api/modify'
import { useAppState } from '../state'

export default function ModifyPage() {
  const { analysis, approved } = useAppState()
  const [res, setRes] = useState<ModifyResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!analysis) return
    modify(analysis.filename, analysis.source).then(setRes).catch((e) => setError(String(e.message ?? e)))
  }, [analysis])

  if (!analysis) {
    return <p className="text-sm text-slate-600">Upload an agent first. <Link to="/" className="text-indigo-700 underline">Go to upload</Link></p>
  }

  async function download() {
    if (!analysis || !approved) return
    setError(null)
    try {
      await downloadBundle(analysis.filename, analysis.source, approved.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="font-semibold">Patched agent: {analysis.filename}</h2>
      {error && <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</div>}
      {res && (
        <>
          <p className="text-sm text-slate-700" data-testid="modify-summary">
            {res.guarded.length} tool(s) guarded, <b>+{res.added_lines}</b> lines added, <b>{res.removed_lines}</b> removed.
            {res.already_guarded.length > 0 && ` Already guarded: ${res.already_guarded.join(', ')}.`}
          </p>
          {res.skipped.length > 0 && (
            <ul className="rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
              {res.skipped.map((s) => <li key={s}>⚠ {s}</li>)}
            </ul>
          )}
          <div className="overflow-hidden rounded border border-slate-300">
            <DiffEditor height="460px" language="python" original={analysis.source} modified={res.patched_source}
              options={{ readOnly: true, renderSideBySide: true, minimap: { enabled: false }, automaticLayout: true }} />
          </div>
          <div className="flex items-center gap-3">
            <button onClick={download} disabled={!approved}
              className="rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">
              Download patched bundle (.zip)
            </button>
            {!approved && <span className="text-xs text-slate-500">Approve a policy on the Review page first: the bundle contains it.</span>}
          </div>
        </>
      )}
    </div>
  )
}
