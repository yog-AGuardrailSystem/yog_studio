import { useEffect, useRef, useState } from 'react'
import {
  benchmarkLatest, cancelTranslate, compareCLexer, explain, pollTranslate, retrieve, startTranslate,
  type CLexerResponse, type CompileInfo, type Diagnostic, type Info, type QueryResult, type Readback, type Retrieved, type RunResponse,
} from '../../api/compile'
import type { PolicyDraft } from '../../api/types'
import { Burst } from '../motion/Burst'
import { applyFix, resultLabel } from '../../lib/workbench'

const chip = 'inline-block rounded px-1.5 py-0.5 font-mono text-xs'
const err = (e: unknown) => (e instanceof Error ? e.message : String(e))

// ---------------------------------------------------------------- tokens
const KIND_COLOUR: Record<string, string> = {
  FACT: 'bg-sky-900 text-sky-100', RULE: 'bg-sky-900 text-sky-100', ALLOW: 'bg-emerald-900 text-emerald-100',
  DENY: 'bg-red-900 text-red-100', QUERY: 'bg-violet-900 text-violet-100', NOT: 'bg-amber-900 text-amber-100',
}
export function TokensPanel({ info }: { info: CompileInfo | null }) {
  if (!info) return <p className="text-sm text-slate-500">Compiling…</p>
  if (!info.tokens.length) return <p className="text-sm text-slate-500">No tokens yet: type some YOG on the left.</p>
  const lines = new Map<number, typeof info.tokens>()
  info.tokens.forEach((t) => lines.set(t.line, [...(lines.get(t.line) ?? []), t]))
  return (
    <div data-testid="tokens-panel">
      <p className="mb-2 text-sm text-slate-500">{info.tokens.length} tokens. This is what the lexer hands to the parser.</p>
      <div className="max-h-[460px] space-y-1 overflow-auto">
        {[...lines.entries()].map(([line, toks]) => (
          <div key={line} className="flex flex-wrap items-center gap-1">
            <span className="w-8 shrink-0 text-right text-xs text-slate-500">{line}</span>
            {toks.map((t, i) => (
              <span key={i} className={`${chip} rise ${KIND_COLOUR[t.kind] ?? 'bg-slate-200 text-slate-800'}`} style={{ animationDelay: `${Math.min(line * 40 + i * 25, 900)}ms` }} data-motion={`wb:token:${line}:${i}`} title={t.kind}>
                {t.value != null && t.value !== '' ? String(t.value) : t.kind}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- AST
function Node({ k, v, depth }: { k: string; v: unknown; depth: number }) {
  if (v && typeof v === 'object') {
    const entries = Array.isArray(v) ? v.map((x, i) => [String(i), x] as const) : Object.entries(v as object)
    return (
      <details open={depth < 2} className="ml-3 rise" style={{ animationDelay: `${depth * 90}ms` }} data-motion={`wb:ast:${depth}:${k}`}>
        <summary className="cursor-pointer text-sm text-slate-700">
          <span className="font-mono">{k}</span> <span className="text-slate-500">{Array.isArray(v) ? `[${entries.length}]` : '{…}'}</span>
        </summary>
        {entries.map(([ek, ev]) => <Node key={ek} k={ek} v={ev} depth={depth + 1} />)}
      </details>
    )
  }
  return <div className="ml-6 rise text-sm" data-motion={`wb:ast-leaf:${depth}:${k}`}><span className="font-mono text-slate-500">{k}:</span> <span className="font-mono text-slate-800">{JSON.stringify(v)}</span></div>
}
export function AstPanel({ info }: { info: CompileInfo | null }) {
  if (!info?.ast) return <p className="text-sm text-slate-500">The tree appears once the program parses.</p>
  return <div className="max-h-[480px] overflow-auto" data-testid="ast-panel"><Node k="program" v={info.ast} depth={0} /></div>
}

// ---------------------------------------------------------------- checks (friendly errors)
export function ChecksPanel({ info, source, onFix, onJump }: {
  info: CompileInfo | null; source: string; onFix: (next: string) => void; onJump: (line: number) => void
}) {
  if (!info) return <p className="text-sm text-slate-500">Compiling…</p>
  return (
    <div data-testid="checks-panel">
      {info.ok ? (
        <p className="pop-in rounded border border-emerald-700 bg-emerald-50 p-3 text-sm text-emerald-800" role="status" data-motion="wb:compiles-badge">
          ✓ Compiles. Tokenizer, parser and semantic check all pass ({info.predicates.length} predicates).
        </p>
      ) : (
        <ul className="space-y-3">
          {info.diagnostics.map((d: Diagnostic, i) => {
            const next = applyFix(source, d)
            return (
              <li key={i} className="shake rounded border border-red-700 bg-red-50 p-3 text-sm" data-testid="diagnostic" data-motion={`wb:diagnostic:${i}`}>
                <div className="font-semibold text-red-800">
                  {d.line ? <button type="button" className="underline" onClick={() => onJump(d.line!)}>Line {d.line}</button> : 'Program'}: {d.hint ?? d.message}
                </div>
                {d.hint && <div className="mt-1 font-mono text-xs text-slate-500">engine said: {d.message}</div>}
                {d.suggestion && <div className="mt-1 text-slate-700">{d.suggestion}</div>}
                {next && (
                  <button type="button" className="btn-secondary mt-2" onClick={() => onFix(next)} data-testid="apply-fix">
                    Fix it: change “{d.fix!.find}” to “{d.fix!.replace}”
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {info.predicates.length > 0 && (
        <table className="mt-4 w-full text-left text-sm">
          <thead className="text-slate-500"><tr><th className="py-1">Predicate</th><th>Kind</th><th>Clauses</th></tr></thead>
          <tbody>
            {info.predicates.map((p) => (
              <tr key={p.name + p.arity} className="border-t border-slate-200">
                <td className="py-1 font-mono">{p.name}/{p.arity}</td><td>{p.role}</td><td>{p.clauses}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- queries, tests and "why?"
export function TestsPanel({ run, source, decisions, adhoc, setAdhoc, onWhy, why }: {
  run: RunResponse | null; source: string; decisions: string[]
  adhoc: { actor: string; action: string; resource: string; context: string }
  setAdhoc: (a: { actor: string; action: string; resource: string; context: string }) => void
  onWhy: (r: { reason: string; trace: string[] } | null) => void; why: string | null
}) {
  const [open, setOpen] = useState<number | null>(null)
  if (!run) return <p className="text-sm text-slate-500">Running…</p>
  if (!run.ok) return <p className="text-sm text-slate-600">Fix the errors in the Checks tab first; then your queries run here.</p>
  const show = (r: QueryResult) => {
    setOpen(open === r.line ? null : r.line)
    onWhy(open === r.line ? null : { reason: r.reason, trace: r.trace })
  }
  return (
    <div data-testid="tests-panel">
      <p className="mb-2 text-sm text-slate-600" data-testid="test-summary">
        {run.results.length} queries · <b className="text-green-700">{run.passed} passed</b> · <b className={run.failed ? 'text-red-700' : ''}>{run.failed} failed</b> · {run.untested} without an expectation
        <span className="block text-xs text-slate-500">Add <code># -&gt; DENY</code> (or ALLOW/TRUE/FALSE) after a query to make it a test.</span>
      </p>
      {run.results.length > 0 && run.failed === 0 && run.passed === run.results.length && (
        <div className="relative h-0" data-testid="all-green"><Burst key={run.results.length + ':' + run.passed} /></div>
      )}
      <ul className="space-y-1">
        {run.results.map((r) => (
          <li key={`${r.line}-${r.decision}-${r.answer}`} className="flip rounded border border-slate-200 bg-white p-2 text-sm" data-motion={`wb:test:${r.line}`} style={{ animationDelay: `${(r.line % 12) * 40}ms` }}>
            <button type="button" className="flex w-full items-center gap-2 text-left" onClick={() => show(r)} aria-expanded={open === r.line} data-testid="query-row">
              <span className={`${chip} ${resultLabel(r) === 'ALLOW' || resultLabel(r) === 'TRUE' ? 'bg-[#047857] text-on-accent' : 'bg-[#b91c1c] text-on-accent'}`}>{resultLabel(r)}</span>
              <span className="font-mono">{r.text}</span>
              {r.passed === true && <span className="ml-auto text-green-700">✓ as expected</span>}
              {r.passed === false && <span className="ml-auto text-red-700">✗ expected {r.expected}</span>}
            </button>
            {open === r.line && (
              <div className="mt-2 border-t border-slate-200 pt-2 text-xs" data-testid="why-box">
                <div className="font-semibold">Why: {r.reason}</div>
                {r.trace.length > 0 && <pre className="mt-1 whitespace-pre-wrap font-mono text-slate-600">{r.trace.join('\n')}</pre>}
                <div className="mt-1 text-slate-500">The deciding clause is highlighted in the editor.</div>
              </div>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-4 rounded border border-slate-200 p-3">
        <h3 className="mb-2 text-sm font-semibold">Try a request</h3>
        <div className="grid grid-cols-3 gap-2 text-sm">
          <label>Actor<input className="field" value={adhoc.actor} onChange={(e) => setAdhoc({ ...adhoc, actor: e.target.value })} /></label>
          <label>Action
            <select className="field" value={adhoc.action} onChange={(e) => setAdhoc({ ...adhoc, action: e.target.value })}>
              {decisions.map((d) => <option key={d}>{d}</option>)}
            </select>
          </label>
          <label>Resource<input className="field" value={adhoc.resource} onChange={(e) => setAdhoc({ ...adhoc, resource: e.target.value })} /></label>
        </div>
        <label className="mt-2 block text-sm">Context facts (one per line, e.g. <code>hour(now, 3)</code>)
          <textarea className="field h-14 font-mono" value={adhoc.context} onChange={(e) => setAdhoc({ ...adhoc, context: e.target.value })} />
        </label>
        {run.adhoc_error && <p className="mt-2 text-sm text-red-700" role="alert">{run.adhoc_error}</p>}
        {run.adhoc && (
          <div className="mt-2 text-sm" data-testid="adhoc-result">
            <span className={`${chip} ${run.adhoc.decision === 'ALLOW' ? 'bg-[#047857] text-on-accent' : 'bg-[#b91c1c] text-on-accent'}`}>{run.adhoc.decision}</span>{' '}
            {run.adhoc.reason}
            <button type="button" className="link ml-3 text-xs" onClick={() => onWhy(why ? null : { reason: run.adhoc!.reason, trace: run.adhoc!.trace })} data-testid="why-adhoc">
              {why ? 'Hide' : 'Why?'} (highlight in editor)
            </button>
          </div>
        )}
      </div>
      <span hidden>{source.length}</span>
    </div>
  )
}

// ---------------------------------------------------------------- readback
export function ReadbackPanel({ source, ok }: { source: string; ok: boolean }) {
  const [rb, setRb] = useState<Readback | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!ok) { setRb(null); return }
    let alive = true
    explain(source).then((r) => { if (alive) { setRb(r.readback); setError(r.valid ? null : r.errors.join('; ')) } }).catch((e) => alive && setError(err(e)))
    return () => { alive = false }
  }, [source, ok])
  if (!ok) return <p className="text-sm text-slate-500">Available once the program compiles.</p>
  if (error) return <p className="text-sm text-red-700" role="alert">{error}</p>
  if (!rb) return <p className="text-sm text-slate-500">Reading it back…</p>
  return (
    <div className="space-y-3 text-sm" data-testid="readback-panel">
      <p className="text-slate-500">Built from the parsed program, not by an AI: every clause appears, nothing is invented.</p>
      {rb.actions.map((a) => (
        <div key={a.predicate} className="rounded border border-slate-200 bg-white p-3">
          <div className="font-semibold">{a.action} <span className="font-mono text-xs text-slate-500">({a.predicate})</span></div>
          {a.allow.map((t, i) => <div key={'a' + i} className="mt-1 text-green-700">Allowed when {t}</div>)}
          {a.deny.map((t, i) => <div key={'d' + i} className="mt-1 text-red-700">Denied when {t}</div>)}
        </div>
      ))}
      {rb.definitions.length > 0 && <div><b>Definitions</b><ul className="ml-5 list-disc">{rb.definitions.map((d, i) => <li key={i}>{d}</li>)}</ul></div>}
      {rb.facts.length > 0 && <div><b>Facts</b><ul className="ml-5 list-disc">{rb.facts.map((d, i) => <li key={i}>{d}</li>)}</ul></div>}
      {rb.notes.map((n, i) => <p key={i} className="text-slate-500">{n}</p>)}
      <p className="text-slate-500">DENY beats ALLOW. If no allow clause applies, the answer is DENY.</p>
    </div>
  )
}

// ---------------------------------------------------------------- C lexer side by side
export function CLexerPanel({ source, available }: { source: string; available: boolean }) {
  const [res, setRes] = useState<CLexerResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function go() {
    setBusy(true); setError(null)
    try { setRes(await compareCLexer(source)) } catch (e) { setError(err(e)) } finally { setBusy(false) }
  }
  return (
    <div className="text-sm" data-testid="clexer-panel">
      <p className="mb-2 text-slate-600">Runs your program through the engine team’s real C lexer and compares every token with the Python reference.</p>
      {!available && <p className="mb-2 rounded border border-amber-600 bg-amber-50 p-2 text-amber-900">The C lexer binary is not available on this server, so only the Python reference runs here.</p>}
      <button type="button" className="btn-secondary" onClick={go} disabled={busy}>{busy ? 'Comparing…' : 'Compare with the C lexer'}</button>
      {error && <p className="mt-2 text-red-700" role="alert">{error}</p>}
      {res && <pre className="mt-3 max-h-80 overflow-auto rounded bg-slate-100 p-2 font-mono text-xs">{JSON.stringify(res, null, 2)}</pre>}
    </div>
  )
}

// ---------------------------------------------------------------- Assist: English -> retrieval -> draft
interface Ev { phase?: string; n?: number; state?: string; errors?: string[]; scenario_failures?: string[]; compiled?: boolean; examples?: { id: string; score: number }[]; count?: number; valid?: boolean; error?: string; verified?: boolean | null }
export function AssistPanel({ info, current, onInsert, onReplace }: {
  info: Info | null; current: string; onInsert: (yog: string) => void; onReplace: (yog: string) => void
}) {
  const [english, setEnglish] = useState('')
  const [found, setFound] = useState<Retrieved[] | null>(null)
  const [events, setEvents] = useState<Ev[]>([])
  const [draft, setDraft] = useState<PolicyDraft | null>(null)
  const [status, setStatus] = useState<'idle' | 'running' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const job = useRef<{ id: string; stop: boolean } | null>(null)
  useEffect(() => () => { if (job.current) job.current.stop = true }, [])

  async function find() {
    setError(null)
    try { setFound((await retrieve(english, [], 3)).results) } catch (e) { setError(err(e)) }
  }
  async function draftIt() {
    setStatus('running'); setError(null); setDraft(null); setEvents([])
    try {
      const { job_id } = await startTranslate([english])
      job.current = { id: job_id, stop: false }
      let since = 0
      while (!job.current.stop) {
        const v = await pollTranslate(job_id, since)
        since = v.next
        if (v.events.length) setEvents((e) => [...e, ...(v.events as Ev[])])
        const ex = (v.events as Ev[]).find((e) => e.phase === 'retrieved')?.examples
        if (ex) setFound((f) => f ?? ex.map((x) => ({ id: x.id, score: x.score, english: '', tools_context: [], gold_yog: '', source: '' })))
        if (v.status !== 'running') {
          if (v.status === 'done') setDraft(v.result)
          if (v.status === 'error') setError(v.error)
          setStatus(v.status === 'error' ? 'error' : 'idle')
          return
        }
        await new Promise((r) => setTimeout(r, 600))
      }
    } catch (e) { setError(err(e)); setStatus('error') }
  }
  async function cancel() {
    if (!job.current) return
    job.current.stop = true
    try { await cancelTranslate(job.current.id) } catch { /* already finished */ }
    setStatus('idle')
  }
  const attempts = events.filter((e) => e.phase === 'attempt' && e.state === 'checked')
  return (
    <div className="space-y-3 text-sm" data-testid="assist-panel">
      {info?.offline_demo && (
        <p className="rounded border border-amber-600 bg-amber-50 p-2 text-amber-900" data-testid="offline-badge" role="note">
          Offline demo mode: no AI model is configured, so drafts are copied from the nearest example, not translated. Add a Gemini or Claude key in backend/.env for real drafts.
        </p>
      )}
      <label className="block">Describe a rule in plain English
        <textarea className="field h-20" value={english} onChange={(e) => setEnglish(e.target.value)} placeholder="e.g. Contractors may never delete files in production." data-testid="assist-input" />
      </label>
      <div className="flex gap-2">
        <button type="button" className="btn-secondary" onClick={find} disabled={!english.trim()} data-testid="assist-find">Find similar examples</button>
        <button type="button" className="btn-primary" onClick={draftIt} disabled={!english.trim() || status === 'running'} data-testid="assist-draft">{status === 'running' ? 'Drafting…' : 'Draft YOG'}</button>
        {status === 'running' && <button type="button" className="btn-secondary" onClick={cancel}>Cancel</button>}
      </div>
      {error && <p className="text-red-700" role="alert">{error}</p>}
      {found && (
        <div data-testid="retrieved-list">
          <b>Most similar examples</b>
          <ul className="mt-1 space-y-1">
            {found.map((r) => (
              <li key={r.id} className="rounded border border-slate-200 bg-white p-2">
                <div className="flex items-center gap-2"><span className="font-mono text-xs">{r.id}</span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded bg-slate-200"><span className="bar-grow block h-full bg-sky-500" data-motion={`wb:ret:${r.id}`} style={{ width: `${Math.max(2, Math.round(r.score * 100))}%` }} /></span>
                  <span className="text-xs text-slate-500">{r.score.toFixed(2)}</span></div>
                {r.english && <div className="text-slate-600">{r.english}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {events.length > 0 && (
        <ol className="space-y-1 text-xs text-slate-600" data-testid="attempt-log">
          {events.filter((e) => e.phase === 'scenarios' && e.state === 'ready').map((e, i) => <li key={'s' + i}>Wrote {e.count} independent test scenarios from your English.</li>)}
          {attempts.map((e, i) => (
            <li key={i} className="rise" data-motion={`wb:attempt:${i}`}>Attempt {e.n}: {e.compiled ? 'compiles' : 'does not compile'}{e.errors?.length ? ` (${e.errors[0]})` : ''}{e.scenario_failures?.length ? `; ${e.scenario_failures.length} scenario(s) disagree` : ''}</li>
          ))}
        </ol>
      )}
      {draft && (
        <div className="pop-in rounded border border-slate-300 p-3" data-testid="draft-box" data-motion="wb:draft-card">
          <div className="mb-1 font-semibold">Draft {draft.valid ? '' : '(does not compile yet)'}
            {draft.verified === true && <span className={`${chip} ml-2 bg-[#047857] text-on-accent`}>checked against independent scenarios</span>}
            {draft.verified === false && <span className={`${chip} ml-2 bg-[#92400e] text-on-accent`}>scenarios disagree: review carefully</span>}
          </div>
          <pre className="max-h-64 overflow-auto rounded bg-slate-100 p-2 font-mono text-xs">{draft.yog_source}</pre>
          <p className="mt-1 text-xs text-slate-500">A draft is a suggestion. Read it, then choose how it enters the editor.</p>
          <div className="mt-2 flex gap-2">
            <button type="button" className="btn-primary" onClick={() => onInsert(draft.yog_source)} data-testid="draft-insert">Add to the end of my program</button>
            <button type="button" className="btn-secondary" onClick={() => { if (!current.trim() || window.confirm('Replace everything in the editor with this draft?')) onReplace(draft.yog_source) }}>Replace my program</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- benchmark evidence
type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
export function BenchmarkPanel() {
  const [data, setData] = useState<{ evaluation: Dict | null; retrieval: Dict | null; note: string | null } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { benchmarkLatest().then(setData).catch((e) => setError(err(e))) }, [])
  if (error) return <p className="text-sm text-red-700" role="alert">{error}</p>
  if (!data) return <p className="text-sm text-slate-500">Loading…</p>
  const ev = data.evaluation
  const rt = data.retrieval
  return (
    <div className="space-y-3 text-sm" data-testid="benchmark-panel">
      {!ev && !rt && <p className="rounded border border-slate-300 p-3 text-slate-600">{data.note}</p>}
      {rt && (
        <div><b>Retrieval</b> ({rt.provider}): recall@1 {rt.overall?.['recall@1']?.pct}% · recall@3 {rt.overall?.['recall@3']?.pct}% · MRR {rt.overall?.mrr}</div>
      )}
      {ev && (
        <table className="w-full text-left"><thead className="text-slate-500"><tr><th>Configuration</th><th>Syntax valid</th><th>Semantically correct</th></tr></thead>
          <tbody>{Object.entries(ev.results as Dict).map(([name, r]) => (
            <tr key={name} className="border-t border-slate-200"><td className="py-1">{name}</td><td>{r.summary.syntax_valid.pct}%</td><td>{r.summary.semantic_correct.pct}% <span className="text-xs text-slate-500">(95% CI {r.summary.semantic_correct.ci_low}–{r.summary.semantic_correct.ci_high})</span></td></tr>
          ))}</tbody></table>
      )}
      {ev && (ev.interpretation as string[]).map((n, i) => <p key={i} className="text-xs text-slate-500">{n}</p>)}
    </div>
  )
}
