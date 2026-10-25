import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { evaluate, type EvalReport, type Scenario, type ScenarioResult } from '../api/evaluate'
import { approve, explain, reject } from '../api/policies'
import type { ExplainResponse } from '../api/types'
import { CodeView } from '../components/CodeView'
import { EvalTable } from '../components/EvalTable'
import { useAppState } from '../state'

const KIND_STYLE: Record<string, string> = {
  allow: 'border-green-300 bg-green-50',
  deny: 'border-red-300 bg-red-50',
  rule: 'border-blue-200 bg-blue-50',
  fact: 'border-slate-200 bg-white',
}

export default function ReviewPage() {
  const { draft, setDraft, approved, setApproved, tools } = useAppState()
  const [report, setReport] = useState<EvalReport | null>(null)
  const [userScen, setUserScen] = useState<Scenario[]>([])
  const [evaluating, setEvaluating] = useState(false)
  const [source, setSource] = useState(draft?.yog_source ?? '')
  const [editing, setEditing] = useState(false)
  const [info, setInfo] = useState<ExplainResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'approved' | 'rejected'>('idle')
  const [busy, setBusy] = useState(false)

  // re-validate + refresh the readback whenever the text changes (debounced)
  // a report describes one exact policy text: editing the text invalidates it
  useEffect(() => {
    setReport(null)
  }, [source])

  useEffect(() => {
    if (!source.trim()) {
      setInfo(null)
      return
    }
    const t = setTimeout(() => {
      explain(source).then(setInfo).catch((e) => setError(String(e.message ?? e)))
    }, 300)
    return () => clearTimeout(t)
  }, [source])

  if (!draft) {
    return (
      <p className="text-sm text-slate-600">
        No draft yet. <Link to="/rules" className="text-indigo-700 underline">Write rules and generate a draft</Link> first.
      </p>
    )
  }

  const valid = info?.valid === true

  async function runEval(scen: Scenario[] = userScen) {
    if (!draft) return
    setEvaluating(true)
    setError(null)
    try {
      setReport(await evaluate({ yog_source: source, english_rules: draft.english_rules, tools, user_scenarios: scen }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setEvaluating(false)
    }
  }

  function adopt(r: ScenarioResult, flip: boolean) {
    const expected = flip ? (r.actual === 'ALLOW' ? 'DENY' : 'ALLOW') : (r.actual ?? r.expected)
    const next = [...userScen, { actor: r.actor, action: r.action, resource: r.resource, context: r.context,
      expected, source: 'user' as const, unconfirmed: false, note: r.note }]
    setUserScen(next)
    void runEval(next)
  }

  async function doApprove() {
    if (!draft) return
    setBusy(true)
    setError(null)
    try {
      const rec = await approve({
        yog_source: source,
        english_rules: draft.english_rules,
        retrieved_examples: draft.retrieved_examples,
        attempts: draft.attempts,
      })
      setApproved(rec)
      setStatus('approved')
      setEditing(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function doReject() {
    setBusy(true)
    try {
      await reject('rejected in review')
      setDraft(null)
      setStatus('rejected')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded border border-slate-200 bg-white p-3 text-sm">
        <b>Rules you wrote:</b>
        <ol className="ml-5 list-decimal">
          {draft.english_rules.map((r) => <li key={r}>{r}</li>)}
        </ol>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <div className="mb-2 flex items-center gap-3">
            <h2 className="font-semibold">YOG policy</h2>
            <span className={`rounded border px-2 py-0.5 text-xs font-bold ${valid ? 'border-green-300 bg-green-100 text-green-800' : 'border-red-300 bg-red-100 text-red-800'}`} data-testid="valid-badge">
              {info === null ? 'checking…' : valid ? 'compiles' : 'does NOT compile'}
            </span>
            <button className="text-sm text-indigo-700" onClick={() => setEditing(!editing)}>
              {editing ? 'Done editing' : 'Edit'}
            </button>
          </div>
          <CodeView value={source} language="plaintext" readOnly={!editing} onChange={setSource} height="420px" />
          {info && !info.valid && (
            <ul className="mt-2 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert">
              {info.errors.map((e) => <li key={e}>{e}</li>)}
            </ul>
          )}
        </section>

        <section>
          <h2 className="mb-2 font-semibold">What this policy means (plain English)</h2>
          {info?.readback ? (
            <div className="space-y-2" data-testid="readback">
              {info.readback.clauses.map((c) => (
                <div key={`${c.line}-${c.text}`} className={`rounded border p-2 text-sm ${KIND_STYLE[c.kind] ?? ''}`}>
                  <span className="mr-2 font-mono text-xs text-slate-500">line {c.line}</span>
                  {c.text}
                </div>
              ))}
              <ul className="list-disc pl-5 text-xs text-slate-600">
                {info.readback.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Fix the policy to see its readback.</p>
          )}
        </section>
      </div>

      <section>
        <div className="mb-2 flex items-center gap-3">
          <h2 className="font-semibold">Scenario evaluation</h2>
          <button onClick={() => runEval()} disabled={!valid || evaluating}
            className="rounded bg-slate-700 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-40">
            {evaluating ? 'Running…' : 'Run scenarios'}
          </button>
          <span className="text-xs text-slate-500">Probes are unconfirmed until you confirm or flip them.</span>
        </div>
        {report && <EvalTable report={report} onConfirm={(r) => adopt(r, false)} onFlip={(r) => adopt(r, true)} />}
      </section>

      {error && <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</div>}

      <div className="flex items-center gap-3 border-t border-slate-200 pt-4">
        <button
          onClick={doApprove}
          disabled={!valid || busy || !report}
          title={report ? '' : 'Run the scenarios first: you approve a policy only after seeing how it behaves'}
          className="rounded bg-green-600 px-5 py-2 text-sm font-bold text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Approve
        </button>
        <button onClick={() => setEditing(true)} className="rounded border border-slate-300 bg-white px-4 py-2 text-sm">
          Edit
        </button>
        <button onClick={doReject} disabled={busy} className="rounded border border-red-300 bg-white px-4 py-2 text-sm text-red-700">
          Reject
        </button>
        {status === 'approved' && approved && (
          <span className="text-sm font-semibold text-green-700" data-testid="approved-msg">
            Approved and saved as {approved.id}
          </span>
        )}
        {status === 'rejected' && <span className="text-sm text-red-700">Draft rejected: nothing was saved.</span>}
      </div>
    </div>
  )
}
