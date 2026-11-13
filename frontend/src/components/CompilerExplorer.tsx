import { useEffect, useRef, useState } from 'react'
import { compareCLexer, compile, runProgram, teamExamples, type CLexerResponse, type CompileInfo, type RunResponse, type TeamGroup } from '../api/compile'

const SAMPLE = `fact employee(r_alice)
fact confidential(payroll_doc)

allow can_access(User, Doc):
    employee(User)

deny can_access(User, Doc):
    employee(User)
    confidential(Doc)

query can_access(r_alice, normal_doc)     # -> ALLOW
query can_access(r_alice, payroll_doc)    # -> DENY
`

const TABS = ['Decisions', 'Tokens', 'Tree', 'Checks'] as const
type Tab = (typeof TABS)[number]

/** Wanted by the landing page: lets an example card load a program into the explorer. */
export const EXPLORER_LOAD_EVENT = 'yog:explorer-load'

/**
 * The live compiler. Every number and result on it comes from the running engine (/compile, /run, /compile/c-lexer).
 * If the server is asleep it says so quietly and keeps the last result on screen; it never invents output.
 */
export function CompilerExplorer({ initial }: { initial?: string }) {
  const [source, setSource] = useState(initial ?? SAMPLE)
  const [tab, setTab] = useState<Tab>('Decisions')
  const [info, setInfo] = useState<CompileInfo | null>(null)
  const [run, setRun] = useState<RunResponse | null>(null)
  const [c, setC] = useState<CLexerResponse | null>(null)
  const [groups, setGroups] = useState<TeamGroup[]>([])
  const [online, setOnline] = useState<boolean | null>(null)
  const seq = useRef(0)

  useEffect(() => { teamExamples().then(setGroups).catch(() => undefined) }, [])
  useEffect(() => {
    const on = (e: Event) => { const s = (e as CustomEvent<string>).detail; if (typeof s === 'string') setSource(s) }
    window.addEventListener(EXPLORER_LOAD_EVENT, on)
    return () => window.removeEventListener(EXPLORER_LOAD_EVENT, on)
  }, [])

  useEffect(() => {
    const mine = ++seq.current
    const t = setTimeout(async () => {
      try {
        const ci = await compile(source)
        if (mine !== seq.current) return
        setInfo(ci); setOnline(true)
        const [r, cl] = await Promise.all([runProgram(source), compareCLexer(source).catch(() => null)])
        if (mine !== seq.current) return
        setRun(r); setC(cl)
      } catch {
        if (mine === seq.current) setOnline(false)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [source])

  const lines = new Map<number, NonNullable<CompileInfo['tokens']>>()
  info?.tokens.forEach((t) => lines.set(t.line, [...(lines.get(t.line) ?? []), t]))
  const cMatch = c?.available && typeof c.compared === 'number' ? `${c.compared} tokens compared with the C lexer, ${(c.mismatches as unknown[] | undefined)?.length ?? 0} differences` : null

  return (
    <div className="glass overflow-hidden" data-testid="explorer" data-online={String(online)}>
      <div className="flex flex-wrap items-center gap-1 border-b border-white/10 p-2">
        {groups.slice(0, 18).map((g) => (
          <button key={g.id} type="button" className="chip" title={g.english} onClick={() => setSource(g.source)} data-testid={`explorer-ex-${g.id.replace('/', '')}`}>
            {g.id}
          </button>
        ))}
        <span className="ml-auto pr-2 text-xs text-slate-400" role="status">
          {online === false ? 'Reconnecting to the compiler…' : online === null ? 'Starting…' : info?.ok ? 'Compiles' : 'Has errors'}
        </span>
      </div>
      <div className="grid md:grid-cols-2">
        <label className="block border-b border-white/10 md:border-b-0 md:border-r">
          <span className="sr-only">YOG source</span>
          <textarea
            value={source} onChange={(e) => setSource(e.target.value)} spellCheck={false} data-testid="explorer-input"
            className="h-80 w-full resize-none bg-transparent p-4 font-mono text-[13px] leading-relaxed text-sky-100 outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
          />
        </label>
        <div className="min-w-0 p-3">
          <div role="tablist" className="mb-3 flex gap-1">
            {TABS.map((t) => (
              <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => setTab(t)} data-testid={`explorer-tab-${t}`}
                className={`rounded px-2.5 py-1 text-sm ${tab === t ? 'bg-sky-900/70 font-semibold text-white' : 'text-slate-300 hover:text-white'}`}>{t}</button>
            ))}
          </div>
          <div className="h-[17rem] overflow-auto pr-1 text-sm" role="tabpanel" data-testid="explorer-output">
            {tab === 'Decisions' && (
              !run ? <p className="text-slate-400">Waiting for the compiler…</p> :
              !run.ok ? <ul className="space-y-2">{run.diagnostics.map((d, i) => <li key={i} className="rounded border border-red-500/50 bg-red-950/40 p-2 text-red-200">{d.line ? `Line ${d.line}${d.column ? `:${d.column}` : ''}: ` : ''}{d.hint ?? d.message}</li>)}</ul> :
              <ul className="space-y-1.5">
                {run.results.map((r) => {
                  const label = r.kind === 'decision' ? r.decision : r.answer ? 'TRUE' : 'FALSE'
                  const good = label === 'ALLOW' || label === 'TRUE'
                  return (
                    <li key={r.line} className="rounded border border-white/10 p-2" data-testid="explorer-result">
                      <span className={`mr-2 inline-block rounded px-1.5 py-0.5 font-mono text-xs font-bold ${good ? 'bg-emerald-700 text-white' : 'bg-red-700 text-white'}`}>{label}</span>
                      <span className="font-mono text-slate-200">{r.text}</span>
                      <div className="mt-1 text-xs text-slate-400">{r.reason}</div>
                    </li>
                  )
                })}
                {!run.results.length && <li className="text-slate-400">No queries yet. Add a line like <code>query can_access(alice, doc1)</code>.</li>}
              </ul>
            )}
            {tab === 'Tokens' && (
              <div className="space-y-1" data-testid="explorer-tokens">
                {[...lines.entries()].map(([ln, toks]) => (
                  <div key={ln} className="flex flex-wrap items-center gap-1">
                    <span className="w-6 text-right text-xs text-slate-500">{ln}</span>
                    {toks.map((t, i) => <span key={i} className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-xs text-sky-200" title={t.kind}>{t.value != null && t.value !== '' ? String(t.value) : t.kind}</span>)}
                  </div>
                ))}
                {cMatch && <p className="pt-2 text-xs text-emerald-300" data-testid="explorer-clexer">{cMatch}.</p>}
                {c && !c.available && <p className="pt-2 text-xs text-slate-400">The C lexer is not available on this server; tokens above come from the Python reference.</p>}
              </div>
            )}
            {tab === 'Tree' && <pre className="font-mono text-xs text-slate-200" data-testid="explorer-ast">{info?.ast ? JSON.stringify(info.ast, null, 1) : 'The tree appears once the program parses.'}</pre>}
            {tab === 'Checks' && (
              <div>
                <p className={info?.ok ? 'text-emerald-300' : 'text-amber-300'}>{info ? (info.ok ? 'Tokenizer, parser and semantic check all pass.' : `${info.diagnostics.length} problem(s)`) : '…'}</p>
                <table className="mt-2 w-full text-left text-xs"><tbody>
                  {info?.predicates.map((p) => <tr key={p.name + p.arity} className="border-t border-white/10"><td className="py-1 font-mono">{p.name}/{p.arity}</td><td>{p.role}</td><td>{p.clauses} clause(s)</td></tr>)}
                </tbody></table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
