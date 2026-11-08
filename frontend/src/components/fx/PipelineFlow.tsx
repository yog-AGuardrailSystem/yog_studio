import { useInView } from 'motion/react'
import { useRef } from 'react'
import { m } from '../../lib/motion'

export interface Stage { name: string; sample: string }

const CYCLE = 9 // seconds for one packet to cross every stage

/**
 * The compiler pipeline as a conveyor: a packet crosses the stages, each stage lights as it arrives, the links between
 * stages fill behind it. Pure CSS keyframes (so the global pause control stops them) started once the diagram is visible.
 */
export function PipelineFlow({ steps }: { steps: readonly Stage[] }) {
  const ref = useRef<HTMLOListElement>(null)
  const seen = useInView(ref, { once: true, margin: '-10% 0px' })
  const n = steps.length
  return (
    <div data-testid="pipeline-flow" data-running={String(seen)}>
      <ol ref={ref} className={`pf grid gap-3 sm:grid-cols-3 lg:grid-cols-9 ${seen ? 'pf-run' : ''}`} style={{ ['--n' as string]: n, ['--cycle' as string]: `${CYCLE}s` }}>
        {steps.map((s, i) => (
          <li key={s.name} className="pf-node relative" style={{ ['--i' as string]: i }} {...m(`pipe:node:${i}`)} tabIndex={0}>
            <span className="pf-halo" aria-hidden {...m(`pipe:pulse:${i}`)} />
            {i < n - 1 && <span className="pf-link" aria-hidden {...m(`pipe:link:${i}`)} />}
            <div className="glass relative h-full p-3">
              <p className="font-mono text-[10px] text-slate-500">{i + 1}</p>
              <p className="font-display text-sm font-bold leading-tight" {...m(`pipe:label:${i}`)}>{s.name}</p>
              <p className="pf-sample mt-1 font-mono text-[11px] text-slate-400">{s.sample}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="pf-track mt-4" aria-hidden>
        <span className={`pf-packet ${seen ? 'pf-run' : ''}`} {...m('pipe:packet')} />
        <span className={`pf-packet pf-packet-b ${seen ? 'pf-run' : ''}`} {...m('pipe:packet-trail')} />
      </div>
    </div>
  )
}
