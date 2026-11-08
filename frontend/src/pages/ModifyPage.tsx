import { DiffEditor } from '@monaco-editor/react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadBundle, modify, type ModifyResult } from '../api/modify'
import { EmptyState } from '../components/EmptyState'
import { defineYogTheme, YOG_DARK } from '../components/monacoTheme'
import { PageIntro } from '../components/PageIntro'
import { Skeleton } from '../components/Skeleton'
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
    return <EmptyState title="No agent uploaded yet" text="Upload a Python agent first. Studio then shows exactly which lines it would add." to="/studio" action="Upload an agent" />
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
      <PageIntro step="Step 4 of 5" title="Patch your agent">
        This diff shows the only lines Studio adds so every tool call is checked by YOG first. Your file is not rewritten.
      </PageIntro>
      <h2 className="font-mono text-sm font-semibold">{analysis.filename}</h2>
      {error && <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</div>}
      {!res && !error && (
        <div className="space-y-2" data-testid="modify-loading" role="status" aria-label="Building the patch">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-96 w-full" />
        </div>
      )}
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
            <DiffEditor height="460px" language="python" theme={YOG_DARK} beforeMount={defineYogTheme} keepCurrentOriginalModel keepCurrentModifiedModel original={analysis.source} modified={res.patched_source}
              options={{ readOnly: true, renderSideBySide: true, minimap: { enabled: false }, automaticLayout: true, renderGutterMenu: false, renderMarginRevertIcon: false }} />
          </div>
          <div className="flex items-center gap-3">
            <button onClick={download} disabled={!approved}
              className="rounded bg-sky-700 px-4 py-2 text-sm font-semibold text-on-accent disabled:opacity-40">
              Download patched bundle (.zip)
            </button>
            {!approved && (
              <span className="text-xs text-slate-500" data-testid="download-hint">
                Download is off until you approve a policy, because the bundle contains it. <Link to="/review" className="text-link underline">Go to Review</Link>
              </span>
            )}
          </div>
        </>
      )}
    </div>
  )
}
