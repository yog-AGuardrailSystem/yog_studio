/** Flatten the engine's AST (as returned by /compile) into display rows, in source order. Nothing is invented. */
export interface AstRow { path: string; depth: number; label: string; kind: 'program' | 'fact' | 'clause' | 'atom' | 'not' | 'query' | 'term' }

type Term = { const?: string | number; var?: string; wildcard?: boolean }
const term = (t: Term): string => (t.var ?? (t.wildcard ? '_' : String(t.const)))
const atom = (a: { pred: string; args?: Term[] }) => `${a.pred}(${(a.args ?? []).map(term).join(', ')})`

export function flattenAst(ast: { facts?: unknown[]; clauses?: unknown[]; queries?: unknown[] } | null): AstRow[] {
  if (!ast) return []
  const rows: AstRow[] = [{ path: 'program', depth: 0, label: 'program', kind: 'program' }]
  const items: { line: number; emit: () => void }[] = []
  ;(ast.facts as { pred: string; args: Term[]; line: number }[] | undefined)?.forEach((f, i) =>
    items.push({ line: f.line, emit: () => rows.push({ path: `fact${i}`, depth: 1, label: `fact ${atom(f)}`, kind: 'fact' }) }))
  ;(ast.clauses as { kind: string; head: { pred: string; args: Term[] }; body: { type: string; pred?: string; args?: Term[]; atom?: { pred: string; args: Term[] }; op?: string; left?: Term; right?: Term }[]; line: number }[] | undefined)?.forEach((c, i) =>
    items.push({
      line: c.line,
      emit: () => {
        rows.push({ path: `clause${i}`, depth: 1, label: `${c.kind} ${atom(c.head)}`, kind: 'clause' })
        c.body.forEach((b, j) => {
          if (b.type === 'not' && b.atom) rows.push({ path: `clause${i}.${j}`, depth: 2, label: `not ${atom(b.atom)}`, kind: 'not' })
          else if (b.pred) rows.push({ path: `clause${i}.${j}`, depth: 2, label: atom({ pred: b.pred, args: b.args }), kind: 'atom' })
          else rows.push({ path: `clause${i}.${j}`, depth: 2, label: b.left && b.right ? `${term(b.left)} ${b.op ?? '?'} ${term(b.right)}` : String(b.type), kind: 'atom' })
        })
      },
    }))
  ;(ast.queries as { pred: string; args: Term[]; line: number }[] | undefined)?.forEach((q, i) =>
    items.push({ line: q.line, emit: () => rows.push({ path: `query${i}`, depth: 1, label: `query ${atom(q)}`, kind: 'query' }) }))
  items.sort((a, b) => a.line - b.line).forEach((x) => x.emit())
  return rows
}
