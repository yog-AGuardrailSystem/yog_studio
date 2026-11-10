import { motion, useInView, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'

export interface PipeStep {
  name: string
  sample: string
}

/**
 * Compiler pipeline that lights up node by node when it scrolls into view, with a pulse that
 * travels along the line afterwards. Everything lit (final state) under reduced motion.
 */
export function Pipeline({ steps }: { steps: readonly PipeStep[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-15% 0px' })
  const reduce = useReducedMotion()
  const [lit, setLit] = useState(0)
  useEffect(() => {
    if (reduce || !inView) return
    let i = 0
    const id = setInterval(() => {
      i += 1
      setLit(i)
      if (i >= steps.length) clearInterval(id)
    }, 520)
    return () => clearInterval(id)
  }, [inView, reduce, steps.length])
  const shown = reduce ? steps.length : lit

  return (
    <div ref={ref} data-testid="pipeline" data-lit={shown}>
      <div className="relative mb-4 hidden h-3 md:block" aria-hidden>
        <div className="absolute inset-x-0 top-1/2 h-px bg-slate-700" />
        <motion.div
          className="absolute left-0 top-1/2 h-px bg-gradient-to-r from-sky-400 to-orange-400"
          initial={false}
          animate={{ width: `${(Math.min(shown, steps.length) / steps.length) * 100}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
        {!reduce && shown >= steps.length && (
          <span
            className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full bg-emerald-300 shadow-[0_0_14px_3px_rgba(52,211,153,.8)]"
            style={{ animation: 'travel 3.2s ease-in-out infinite' }}
          />
        )}
      </div>
      <ol className="grid gap-3 md:grid-cols-5">
        {steps.map((s, i) => {
          const on = i < shown
          return (
            <motion.li
              key={s.name}
              className="glass p-4"
              initial={false}
              animate={{
                borderColor: on ? 'rgba(245,185,66,.65)' : 'rgba(148,163,184,.16)',
                boxShadow: on ? '0 0 28px -8px rgba(245,185,66,.6)' : '0 0 0 0 rgba(0,0,0,0)',
                y: on ? 0 : 6,
              }}
              transition={{ duration: 0.4 }}
            >
              <p className={`text-xs font-semibold ${on ? 'text-sky-300' : 'text-slate-500'}`}>{i + 1}</p>
              <p className="font-display text-lg font-bold">{s.name}</p>
              <p className="mt-2 font-mono text-xs text-slate-400">{s.sample}</p>
            </motion.li>
          )
        })}
      </ol>
    </div>
  )
}
