import { m, useCalm } from '../../lib/motion'
import type { PolicyGraph, GraphNode } from '../../api/compile'

/**
 * What one example policy really contains, drawn from the parser's own structure (never from keyword counts):
 * a pill per fact predicate (data), per rule (derived) and per decision (allow/deny), and a line for every body atom
 * that feeds a clause. Dashed = `not`, red = feeds a deny clause, a dimmed fact is never read by any clause.
 * Dots travel along the lines (SVG motion; not drawn when motion is paused or reduced).
 */
const ROW = 22
const PILL_H = 17
const CH = 5.5            // width of one monospace character at the label size
const GAP = 46            // between columns (the lines run through it)
const PAD = 2
const SCALE = 1.18         // every card is drawn at the same scale (shrinks only if the card is too narrow), so text sizes match

const trunc = (s: string, n = 19) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)
const factLabel = (n: GraphNode) => `${trunc(n.pred, 15)}${n.count > 1 ? ` ×${n.count}` : ''}`
const allowText = (n: GraphNode) => (n.allow > 1 ? `ALLOW ×${n.allow}` : 'ALLOW')
const denyText = (n: GraphNode) => (n.deny > 1 ? `DENY ×${n.deny}` : 'DENY')

interface Box { x: number; y: number; w: number }

function describeGraph(g: PolicyGraph): string {
  const facts = g.facts.map((f) => `${f.pred} (${f.count}${f.used ? '' : ', unused'})`).join(', ')
  const dec = g.decisions.map((d) => `${d.pred}: ${d.allow} allow${d.deny ? `, ${d.deny} deny` : ''}${d.compares ? `, ${d.compares} comparison` : ''}`).join('; ')
  const rules = g.rules.length ? ` Rules: ${g.rules.map((r) => r.pred).join(', ')}.` : ''
  return `Facts: ${facts}.${rules} Decisions: ${dec}.`
}

export function CardFlow({ id, graph }: { id: string; graph: PolicyGraph | null | undefined }) {
  const calm = useCalm()
  if (!graph) return null
  const gid = id.replace('/', '')

  const cols: GraphNode[][] = [graph.facts, graph.rules, graph.decisions].filter((c) => c.length)
  const width = (n: GraphNode) => (n.kind === 'decision'
    ? trunc(n.pred).length * CH + 14 + (n.allow ? allowText(n).length * CH + 12 : 0) + (n.deny ? denyText(n).length * CH + 12 : 0) + 4
    : factLabel(n).length * CH + 14)
  const rowsMax = Math.max(...cols.map((c) => c.length))
  const height = rowsMax * ROW + PAD * 2

  const boxes = new Map<string, Box>()
  let x = PAD
  for (const col of cols) {
    const w = Math.max(...col.map(width))
    const top = PAD + ((rowsMax - col.length) * ROW) / 2            // centre each column against the tallest one
    col.forEach((n, i) => boxes.set(n.id, { x, y: top + i * ROW, w }))
    x += w + GAP
  }
  const total = x - GAP + PAD

  return (
    <svg viewBox={`0 0 ${total} ${height}`} className="mt-3 block" style={{ width: `min(100%, ${(total * SCALE).toFixed(0)}px)`, height: 'auto' }}
      role="img" aria-label={describeGraph(graph)} data-testid={`flow-${gid}`}>
      {graph.edges.map((e, i) => {
        const a = boxes.get(e.src), b = boxes.get(e.dst)
        if (!a || !b) return null
        const x1 = a.x + a.w, y1 = a.y + PILL_H / 2, x2 = b.x, y2 = b.y + PILL_H / 2, mx = (x1 + x2) / 2
        const d = `M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`
        return (
          <g key={`${e.src}>${e.dst}>${e.negated}>${e.via}`}>
            <path d={d} fill="none" className={`cf-line ${e.via === 'deny' ? 'cf-line-deny' : ''}`} strokeDasharray={e.negated ? '3 3' : undefined} />
            {!calm && (
              <circle r="2.4" className={e.via === 'deny' ? 'cf-dot cf-dot-deny' : 'cf-dot'} {...m(`card:${gid}:dot:${i}`)}>
                <animateMotion dur="2.6s" begin={`${(i % 5) * 0.45}s`} repeatCount="indefinite" path={d} />
              </circle>
            )}
          </g>
        )
      })}
      {graph.facts.map((n, i) => {
        const b = boxes.get(n.id)!
        return (
          <g key={n.id} className={n.used ? '' : 'cf-dim'} {...m(`card:${gid}:fact:${i}`)}>
            <title>{n.used ? `${n.pred}/${n.arity}: ${n.count} fact${n.count > 1 ? 's' : ''}` : `${n.pred}/${n.arity}: ${n.count} fact${n.count > 1 ? 's' : ''}, never read by any rule`}</title>
            <rect x={b.x} y={b.y} width={b.w} height={PILL_H} rx={PILL_H / 2} className="cf-factpill" strokeDasharray={n.used ? undefined : '2 2'} />
            <text x={b.x + 7} y={b.y + 12} className="cf-label">{factLabel(n)}</text>
          </g>
        )
      })}
      {graph.rules.map((n, i) => {
        const b = boxes.get(n.id)!
        return (
          <g key={n.id} {...m(`card:${gid}:rule:${i}`)}>
            <title>{`${n.pred}/${n.arity}: rule, ${n.count} clause${n.count > 1 ? 's' : ''}`}</title>
            <rect x={b.x} y={b.y} width={b.w} height={PILL_H} rx="5" className="cf-rule" />
            <text x={b.x + 7} y={b.y + 12} className="cf-label">{factLabel(n)}</text>
          </g>
        )
      })}
      {graph.decisions.map((n, i) => {
        const b = boxes.get(n.id)!
        const nameW = trunc(n.pred).length * CH + 14
        const allowX = b.x + nameW
        const denyX = allowX + (n.allow ? allowText(n).length * CH + 12 + 3 : 0)
        return (
          <g key={n.id} {...m(`card:${gid}:decision:${i}`)}>
            <title>{`${n.pred}/${n.arity}: ${n.allow} allow clause${n.allow === 1 ? '' : 's'}${n.deny ? `, ${n.deny} deny clause${n.deny === 1 ? '' : 's'}` : ''}${n.compares ? `, ${n.compares} comparison${n.compares === 1 ? '' : 's'}` : ''}`}</title>
            <rect x={b.x} y={b.y} width={b.w} height={PILL_H} rx={PILL_H / 2} className="cf-decision" />
            <text x={b.x + 7} y={b.y + 12} className="cf-label">{trunc(n.pred)}</text>
            {n.allow > 0 && (
              <g {...m(`card:${gid}:allow:${i}`)}>
                <rect x={allowX} y={b.y + 2.5} width={allowText(n).length * CH + 10} height={PILL_H - 5} rx="6" className="cf-allow" />
                <text x={allowX + 5} y={b.y + 11.5} className="cf-chip">{allowText(n)}</text>
              </g>
            )}
            {n.deny > 0 && (
              <g {...m(`card:${gid}:deny:${i}`)}>
                <rect x={denyX} y={b.y + 2.5} width={denyText(n).length * CH + 10} height={PILL_H - 5} rx="6" className="cf-deny" />
                <text x={denyX + 5} y={b.y + 11.5} className="cf-chip">{denyText(n)}</text>
              </g>
            )}
          </g>
        )
      })}
    </svg>
  )
}
