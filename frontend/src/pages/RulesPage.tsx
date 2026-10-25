import { useState } from 'react'
import { Link } from 'react-router-dom'
import { retrieve, type Retrieved } from '../api/retrieve'
import { translate } from '../api/translate'
import { CodeView } from '../components/CodeView'
import { ExampleCards } from '../components/ExampleCards'
import { HintChip } from '../components/ToolsTable'
import { useAppState } from '../state'

export default function RulesPage() {
  const { tools, rules, setRules, draft, setDraft } = useAppState()
  const [generating, setGenerating] = useState(false)
  const [examples, setExamples] = useState<Retrieved[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const filled = rules.filter((r) => r.trim())

  function setRule(i: number, v: string) {
    setRules(rules.map((r, j) => (j === i ? v : r)))
  }

  async function find() {
    setBusy(true)
    setError(null)
    try {
      const toolNames = tools.map((t) => t.name)
      const lists = await Promise.all(filled.map((r) => retrieve(r, toolNames, 3)))
      // merge across rules, keep best score per example id
      const best = new Map<string, Retrieved>()
      lists.flat().forEach((e) => {
        const cur = best.get(e.id)
        if (!cur || e.score > cur.score) best.set(e.id, e)
      })
      setExamples([...best.values()].sort((a, b) => b.score - a.score).slice(0, 6))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function generate() {
    setGenerating(true)
    setError(null)
    try {
      setDraft(await translate(filled, tools))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-2 font-semibold">Tools the policy will cover</h2>
        {tools.length === 0 ? (
          <p className="text-sm text-slate-500">
            No tools yet. <Link to="/" className="text-indigo-700 underline">Upload an agent first</Link> (or continue without tools).
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {tools.map((t) => (
              <span key={t.name} className="rounded border border-slate-200 bg-white px-2 py-1 text-xs">
                <span className="font-mono font-semibold">{t.name}</span>{' '}
                {t.side_effect_hints.map((h) => <HintChip key={h} hint={h} />)}
              </span>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Rules in plain English</h2>
        <div className="space-y-2">
          {rules.map((r, i) => (
            <div key={i} className="flex gap-2">
              <textarea
                aria-label={`rule ${i + 1}`}
                value={r}
                onChange={(e) => setRule(i, e.target.value)}
                placeholder="e.g. The agent may never unlock the door between 11pm and 6am."
                className="h-14 flex-1 rounded border border-slate-300 bg-white p-2 text-sm"
              />
              {rules.length > 1 && (
                <button className="text-xs text-slate-500 hover:text-red-600" onClick={() => setRules(rules.filter((_, j) => j !== i))}>
                  remove
                </button>
              )}
            </div>
          ))}
        </div>
        <div className="mt-2 flex gap-3">
          <button className="text-sm text-indigo-700" onClick={() => setRules([...rules, ''])}>+ add rule</button>
          <button
            onClick={find}
            disabled={busy || filled.length === 0}
            className="rounded bg-slate-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {busy ? 'Searching…' : 'Find similar examples'}
          </button>
          <button
            onClick={generate}
            disabled={generating || filled.length === 0}
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {generating ? 'Generating…' : 'Generate YOG draft'}
          </button>
        </div>
        {error && <div className="mt-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</div>}
      </section>

      {examples.length > 0 && (
        <section>
          <h2 className="mb-2 font-semibold">Retrieved examples</h2>
          <ExampleCards examples={examples} />
        </section>
      )}
      {draft && (
        <section data-testid="draft-panel">
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <h2 className="font-semibold">Draft policy</h2>
            <span className={`rounded border px-2 py-0.5 text-xs font-bold ${draft.valid ? 'border-green-300 bg-green-100 text-green-800' : 'border-red-300 bg-red-100 text-red-800'}`}>
              {draft.valid ? 'compiles' : 'does NOT compile'}
            </span>
            <span className="text-xs text-slate-500">attempts used: {draft.attempts} / 3</span>
            {draft.retrieved_examples.length > 0 && (
              <span className="text-xs text-slate-500">examples: {draft.retrieved_examples.join(', ')}</span>
            )}
          </div>
          {draft.errors.length > 0 && (
            <ul className="mb-2 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
              {draft.errors.map((e) => <li key={e}>{e}</li>)}
            </ul>
          )}
          <CodeView value={draft.yog_source} language="plaintext" height="280px" />
          <Link to="/review" className="mt-3 inline-block rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">
            Review &amp; approve →
          </Link>
        </section>
      )}
    </div>
  )
}
