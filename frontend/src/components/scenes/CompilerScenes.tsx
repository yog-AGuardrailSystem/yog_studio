import { motion, useInView } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { compile, runProgram, teamExamples, type CompileInfo, type RunResponse } from '../../api/compile'
import { flattenAst } from '../../lib/ast'
import { m, useCalm } from '../../lib/motion'

const FALLBACK = `fact employee(r_alice)
fact confidential(payroll_doc)

allow can_access(User, Doc):
    employee(User)

deny can_access(User, Doc):
    employee(User)
    confidential(Doc)

query can_access(r_alice, payroll_doc)
`

const KIND: Record<string, string> = {
  KW: 'bg-sky-800 text-sky-100', IDENT: 'bg-slate-700 text-slate-100', NUMBER: 'bg-amber-800 text-amber-100',
  STRING: 'bg-amber-800 text-amber-100', NEWLINE: 'bg-slate-800 text-slate-400', INDENT: 'bg-violet-800 text-violet-100',
  DEDENT: 'bg-violet-800 text-violet-100',
}

function Stage({ id, title, blurb, onReplay, children }: { id: string; title: string; blurb: string; onReplay: () => void; children: ReactNode }) {
  return (
    <article className="glass flex min-w-0 flex-col p-4" data-testid={`scene-${id}`} {...m(`scene:${id}:frame`)}>
      <header className="mb-3 flex items-start justify-between gap-2">
        <div><h3 className="font-display text-lg font-bold">{title}</h3><p className="text-sm text-slate-400">{blurb}</p></div>
        <button type="button" className="chip shrink-0" onClick={onReplay} {...m(`scene:${id}:replay`)}>Replay</button>
      </header>
      <div className="min-h-[15rem] flex-1">{children}</div>
    </article>
  )
}

/** Four small scenes that replay the real output of the compiler for one program: lexer, parser, semantic analysis, evaluation. */
export function CompilerScenes() {
  const ref = useRef<HTMLDivElement>(null)
  const seen = useInView(ref, { once: true, margin: '-15% 0px' })
  const calm = useCalm()
  const [src, setSrc] = useState(FALLBACK)
  const [infoRaw, setInfo] = useState<CompileInfo | null>(null)
  const [runRaw, setRun] = useState<RunResponse | null>(null)
  const [round, setRound] = useState<Record<string, number>>({ lexer: 0, parser: 0, semantic: 0, eval: 0 })
  const bump = (k: string) => setRound((r) => ({ ...r, [k]: r[k] + 1 }))

  useEffect(() => { teamExamples().then((g) => { const r = g.find((x) => x.id === 'R'); if (r) setSrc(r.source) }).catch(() => undefined) }, [])
  useEffect(() => {
    let alive = true
    compile(src).then(async (c) => { if (!alive) return; setInfo(c); const r = await runProgram(src); if (alive) setRun(r) }).catch(() => undefined)
    return () => { alive = false }
  }, [src])

  const play = seen && !calm
  const ready = seen || calm // content mounts when visible, so entrance animations really play
  const info = ready ? infoRaw : null
  const run = ready ? runRaw : null
  const toks = (info?.tokens ?? []).filter((t) => t.kind !== 'NEWLINE').slice(0, 56)
  const byLine = new Map<number, typeof toks>()
  toks.forEach((t) => byLine.set(t.line, [...(byLine.get(t.line) ?? []), t]))
  const rows = flattenAst(info?.ast ?? null).slice(0, 28)
  const preds = info?.predicates ?? []
  const decision = run?.results.find((r) => r.kind === 'decision' && r.trace.length) ?? run?.results.find((r) => r.kind === 'decision')
  const steps = (decision?.trace ?? []).slice(0, 12)

  return (
    <div ref={ref} className="grid gap-4 lg:grid-cols-2" data-testid="compiler-scenes" data-live={String(!!infoRaw)}>
      <Stage id="lexer" title="1. Lexer" blurb="Characters become tokens, line by line." onReplay={() => bump('lexer')}>
        <div key={round.lexer} className="space-y-1">
          {[...byLine.entries()].slice(0, 14).map(([ln, ts], li) => (
            <motion.div key={ln} className="flex flex-wrap items-center gap-1" {...m(`scene:lexer:line:${li}`)}
              initial={play ? { backgroundColor: 'rgba(245,185,66,0.25)' } : false} animate={{ backgroundColor: 'rgba(245,185,66,0)' }}
              transition={{ delay: 0.35 * li + 0.1, duration: 0.8 }}>
              <span className="w-5 text-right text-xs text-slate-500">{ln}</span>
              {ts.map((t, i) => {
                const gi = [...byLine.values()].slice(0, li).reduce((n, a) => n + a.length, 0) + i
                return (
                  <motion.span key={i} className={`rounded px-1.5 py-0.5 font-mono text-xs ${KIND[t.kind] ?? 'bg-slate-800 text-sky-200'}`} {...m(`scene:lexer:tok:${gi}`)}
                    initial={play ? { opacity: 0, scale: 0.4, y: -8 } : false} animate={{ opacity: 1, scale: 1, y: 0 }}
                    transition={{ delay: 0.35 * li + 0.04 * i, type: 'spring', stiffness: 380, damping: 18 }} title={t.kind}>
                    {t.value != null && t.value !== '' ? String(t.value) : t.kind}
                  </motion.span>
                )
              })}
            </motion.div>
          ))}
          {!info && <p className="text-sm text-slate-500">Waiting for the compiler…</p>}
        </div>
      </Stage>

      <Stage id="parser" title="2. Parser" blurb="Tokens group into facts, clauses and their conditions." onReplay={() => bump('parser')}>
        <ul key={round.parser} className="space-y-0.5 font-mono text-xs">
          {rows.map((r, i) => (
            <motion.li key={r.path} {...m(`scene:parser:node:${i}`)} style={{ marginLeft: r.depth * 18 }}
              className={`flex items-center gap-2 ${r.kind === 'clause' ? 'text-emerald-200' : r.kind === 'query' ? 'text-violet-200' : r.kind === 'fact' ? 'text-sky-200' : 'text-slate-300'}`}
              initial={play ? { opacity: 0, x: -14 } : false} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 * i, duration: 0.3 }}>
              <span aria-hidden className="inline-block h-px w-3 bg-slate-600" />{r.label}
            </motion.li>
          ))}
          {!info && <li className="text-sm text-slate-500">Waiting for the compiler…</li>}
        </ul>
      </Stage>

      <Stage id="semantic" title="3. Semantic analysis" blurb="Every name used is defined, variables are bound, no rule depends on itself." onReplay={() => bump('semantic')}>
        <table key={round.semantic} className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500"><tr><th>Predicate</th><th>Kind</th><th>Clauses</th><th>Check</th></tr></thead>
          <tbody>
            {preds.map((p, i) => (
              <motion.tr key={p.name + p.arity} className="border-t border-white/10" {...m(`scene:semantic:row:${i}`)}
                initial={play ? { opacity: 0, y: 8 } : false} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 * i }}>
                <td className="py-1.5 font-mono">{p.name}/{p.arity}</td><td>{p.role}</td><td>{p.clauses}</td>
                <td>
                  <motion.span className="inline-block text-emerald-300" {...m(`scene:semantic:tick:${i}`)}
                    initial={play ? { scale: 0, rotate: -90 } : false} animate={{ scale: 1, rotate: 0 }} transition={{ delay: 0.3 * i + 0.25, type: 'spring', stiffness: 500, damping: 14 }}>
                    {info?.ok ? '✓' : '·'}
                  </motion.span>
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
        {!preds.length && <p className="text-sm text-slate-500">Waiting for the compiler…</p>}
      </Stage>

      <Stage id="eval" title="4. Evaluation" blurb={decision ? `Why ${decision.text} is ${decision.decision}.` : 'The engine proves or refuses a goal.'} onReplay={() => bump('eval')}>
        <ol key={round.eval} className="space-y-1 font-mono text-xs">
          {steps.map((s, i) => (
            <motion.li key={i} {...m(`scene:eval:step:${i}`)} className={s.trim().startsWith('?-') ? 'text-sky-200' : 'ml-4 text-emerald-200'}
              initial={play ? { opacity: 0, x: -10 } : false} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.22 * i }}>{s}</motion.li>
          ))}
        </ol>
        {decision && (
          <motion.div {...m('scene:eval:verdict')} className={`mt-3 inline-block rounded border-2 px-3 py-1 font-display text-xl font-extrabold ${decision.decision === 'ALLOW' ? 'border-emerald-400 text-emerald-300' : 'border-red-400 text-red-300'}`}
            initial={play ? { scale: 2.2, opacity: 0, rotate: -6 } : false} animate={{ scale: 1, opacity: 1, rotate: 0 }}
            transition={{ delay: 0.22 * steps.length + 0.2, type: 'spring', stiffness: 420, damping: 16 }}>
            {decision.decision}
          </motion.div>
        )}
        {decision && <p className="mt-2 text-xs text-slate-400">{decision.reason}</p>}
        {!decision && <p className="text-sm text-slate-500">Waiting for the compiler…</p>}
      </Stage>
    </div>
  )
}
