import { useState } from 'react'
import { Link } from 'react-router-dom'
import { retrieve, type Retrieved } from '../api/retrieve'
import { ExampleCards } from '../components/ExampleCards'
import { HintChip } from '../components/ToolsTable'
import { useAppState } from '../state'

export default function RulesPage() {
  const { tools, rules, setRules } = useAppState()
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
        </div>
        {error && <div className="mt-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</div>}
      </section>

      {examples.length > 0 && (
        <section>
          <h2 className="mb-2 font-semibold">Retrieved examples</h2>
          <ExampleCards examples={examples} />
        </section>
      )}
    </div>
  )
}
