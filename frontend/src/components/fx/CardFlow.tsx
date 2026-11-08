import { m, useCalm } from '../../lib/motion'

/** Counts what a program really contains; the picture is drawn from these numbers, nothing else. */
export function shapeOf(source: string) {
  const count = (kw: string) => (source.match(new RegExp(`^${kw}\\b`, 'gm')) ?? []).length
  return { facts: count('fact'), rules: count('rule'), allows: count('allow'), denies: count('deny') }
}

/**
 * A tiny flow for one example: its facts feed its rules, which feed its allow/deny decisions.
 * Dots travel along the arrows (CSS keyframes, stopped by the global pause control).
 */
export function CardFlow({ id, source }: { id: string; source: string }) {
  const s = shapeOf(source)
  const calm = useCalm()
  const facts = Math.min(s.facts, 3)
  const gid = id.replace('/', '')
  return (
    <svg viewBox="0 0 240 56" className="mt-3 h-14 w-full" role="img" aria-label={`${s.facts} facts, ${s.rules} rules, ${s.allows} allow and ${s.denies} deny clauses`} data-testid={`flow-${gid}`}>
      {Array.from({ length: facts }, (_, i) => (
        <g key={i}>
          <circle cx="14" cy={12 + i * 16} r="5" className="cf-fact" {...m(`card:${gid}:fact:${i}`)} />
          <line x1="20" y1={12 + i * 16} x2="96" y2="28" className="cf-line" />
          <circle cx="14" cy={12 + i * 16} r="3" className="cf-dot" style={{ animationDelay: `${i * 0.45}s` }} {...m(`card:${gid}:dot:${i}`)} />
        </g>
      ))}
      <rect x="96" y="18" width="36" height="20" rx="5" className={s.rules ? 'cf-rule' : 'cf-rule cf-dim'} {...m(`card:${gid}:rule`)} />
      <text x="114" y="32" textAnchor="middle" className="cf-label">{s.rules ? `rule${s.rules > 1 ? 's' : ''}` : 'body'}</text>
      <line x1="132" y1="28" x2="170" y2="16" className="cf-line" /><line x1="132" y1="28" x2="170" y2="40" className="cf-line" />
      <rect x="170" y="6" width="58" height="20" rx="10" className={`cf-allow ${s.allows ? '' : 'cf-dim'}`} {...m(`card:${gid}:allow`)} />
      <text x="199" y="20" textAnchor="middle" className="cf-label">ALLOW{s.allows > 1 ? ` ×${s.allows}` : ''}</text>
      <rect x="170" y="30" width="58" height="20" rx="10" className={`cf-deny ${s.denies ? '' : 'cf-dim'}`} {...m(`card:${gid}:deny`)} />
      <text x="199" y="44" textAnchor="middle" className="cf-label">DENY{s.denies > 1 ? ` ×${s.denies}` : ''}</text>
      {!calm && <circle r="3.5" className="cf-beam" {...m(`card:${gid}:beam`)}><animateMotion dur="2.6s" repeatCount="indefinite" path="M96 28 L132 28 L170 16" /></circle>}
    </svg>
  )
}
