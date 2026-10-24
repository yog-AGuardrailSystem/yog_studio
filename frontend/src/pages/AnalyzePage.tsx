import { useEffect, useMemo, useState, type DragEvent } from 'react'
import { Link } from 'react-router-dom'
import { analyzeSource, analyzeUpload, getSample, listSamples } from '../api/analyze'
import type { Tool } from '../api/types'
import { CodeView } from '../components/CodeView'
import { ToolsTable } from '../components/ToolsTable'
import { useAppState } from '../state'

const KIND_LABEL = {
  mcp_server: 'MCP server',
  function_calling_agent: 'Function-calling agent',
  unknown: 'Unknown',
} as const

function evidenceLines(evidence: string[]): number[] {
  return evidence.map((e) => /^line (\d+):/.exec(e)?.[1]).filter(Boolean).map(Number)
}

export default function AnalyzePage() {
  const { analysis, setAnalysis, tools, setTools } = useAppState()
  const [samples, setSamples] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [reveal, setReveal] = useState<number | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())

  useEffect(() => {
    listSamples().then(setSamples).catch(() => setSamples([]))
  }, [])

  const highlight = useMemo(() => (analysis ? evidenceLines(analysis.detect.evidence) : []), [analysis])

  async function run(job: () => Promise<Awaited<ReturnType<typeof analyzeSource>>>) {
    setBusy(true)
    setError(null)
    try {
      const res = await job()
      setAnalysis(res)
      setTools(res.tools)
      setPicked(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) void run(() => analyzeUpload(f))
  }

  function togglePick(name: string) {
    const next = new Set(picked)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    setPicked(next)
    setTools(analysis!.candidates.filter((c) => next.has(c.name)))
  }

  const detect = analysis?.detect
  const badge =
    detect &&
    (detect.kind === 'unknown'
      ? 'bg-amber-100 text-amber-900 border-amber-300'
      : 'bg-green-100 text-green-800 border-green-300')

  return (
    <div className="space-y-6">
      <section
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-lg border-2 border-dashed p-6 text-center ${dragging ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 bg-white'}`}
      >
        <p className="mb-3 text-sm text-slate-600">Drop a Python agent / MCP server file here, or</p>
        <input
          type="file"
          accept=".py"
          aria-label="upload agent file"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) void run(() => analyzeUpload(f))
          }}
          className="text-sm"
        />
        {samples.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-sm">
            <span className="text-slate-500">or try a sample:</span>
            {samples.map((s) => (
              <button
                key={s}
                className="rounded border border-slate-300 bg-white px-2 py-1 font-mono text-xs hover:bg-indigo-50"
                onClick={() => run(async () => {
                  const smp = await getSample(s)
                  return analyzeSource(smp.filename, smp.source)
                })}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {busy && <p className="mt-3 text-sm text-slate-500">Analysing…</p>}
        <p className="mt-3 text-xs text-slate-400">Files are analysed statically. Your code is never executed.</p>
      </section>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert">
          {error}
        </div>
      )}

      {analysis && detect && (
        <>
          <section>
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="font-mono text-sm font-semibold">{analysis.filename}</h2>
              <span className={`rounded border px-2 py-0.5 text-sm font-semibold ${badge}`} data-testid="detect-badge">
                {KIND_LABEL[detect.kind]}
                {detect.kind !== 'unknown' && `, ${detect.confidence.toFixed(2)}`}
              </span>
            </div>
            {detect.kind === 'unknown' && (
              <p className="mt-2 text-sm text-amber-800">
                Could not tell what kind of agent this is — nothing was guessed. Pick the functions that should count as tools below.
              </p>
            )}
            <ul className="mt-2 space-y-0.5 text-xs text-slate-600">
              {detect.evidence.map((e) => (
                <li key={e} className="font-mono">{e}</li>
              ))}
            </ul>
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            <section>
              <h3 className="mb-2 text-sm font-semibold">Source (evidence lines highlighted)</h3>
              <CodeView value={analysis.source} highlightLines={highlight} revealLine={reveal} />
            </section>
            <section>
              <h3 className="mb-2 text-sm font-semibold">
                {detect.kind === 'unknown' ? `Candidate functions (${analysis.candidates.length})` : `Tools found (${analysis.tools.length})`}
              </h3>
              {detect.kind === 'unknown' ? (
                <ToolsTable
                  tools={analysis.candidates}
                  selected={picked}
                  onToggle={togglePick}
                  onSelect={(t: Tool) => setReveal(t.source_line)}
                />
              ) : (
                <ToolsTable tools={analysis.tools} onSelect={(t: Tool) => setReveal(t.source_line)} />
              )}
              {tools.length > 0 && (
                <Link to="/rules" className="mt-4 inline-block rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">
                  Continue with {tools.length} tool{tools.length === 1 ? '' : 's'} →
                </Link>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  )
}
