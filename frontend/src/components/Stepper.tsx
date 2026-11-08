import { motion, useReducedMotion } from 'motion/react'
import { Link, useLocation } from 'react-router-dom'
import { useAppState } from '../state'

interface Step {
  to: string
  label: string
  done: boolean
  /** why it can't be opened yet; undefined = open */
  locked?: string
}

/**
 * The Studio flow as a real stepper: current / done / locked, clickable when open.
 * The active highlight slides between steps and the connector lines fill as steps complete.
 */
export function Stepper() {
  const { analysis, draft, approved } = useAppState()
  const { pathname } = useLocation()
  const reduce = useReducedMotion()

  const steps: Step[] = [
    { to: '/studio', label: 'Upload', done: !!analysis },
    { to: '/rules', label: 'Rules', done: !!draft },
    { to: '/review', label: 'Review', done: !!approved, locked: draft ? undefined : 'Write rules and generate a draft first' },
    { to: '/modify', label: 'Patch', done: false, locked: analysis ? undefined : 'Upload an agent first' },
    { to: '/device', label: 'Device', done: false },
  ]

  return (
    <ol className="flex flex-wrap items-center gap-1 text-sm" aria-label="Progress" data-testid="progress">
      {steps.map((s, i) => {
        const current = pathname === s.to
        const base = 'relative inline-flex items-center gap-2 rounded-full px-3 py-1'
        const num = (
          <span
            className={`relative z-10 flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${
              s.done ? 'bg-emerald-600 text-on-accent' : current ? 'bg-sky-700 text-on-accent' : 'bg-slate-200 text-slate-600'
            }`}
            aria-hidden
          >
            {s.done ? (
              <motion.span key="tick" initial={reduce ? false : { scale: 0, rotate: -90 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: 'spring', stiffness: 500, damping: 18 }}>
                ✓
              </motion.span>
            ) : (
              i + 1
            )}
          </span>
        )
        return (
          <li key={s.to} className="flex items-center gap-1">
            {i > 0 && (
              <span className="relative h-px w-4 overflow-hidden bg-slate-300" aria-hidden>
                <motion.span
                  className="absolute inset-0 origin-left bg-emerald-500"
                  initial={false}
                  animate={{ scaleX: steps[i - 1].done ? 1 : 0 }}
                  transition={{ duration: reduce ? 0 : 0.5 }}
                />
              </span>
            )}
            {s.locked ? (
              <span className={`${base} cursor-not-allowed text-slate-400`} aria-disabled="true" title={s.locked} data-state="locked">
                {num}
                {s.label}
              </span>
            ) : (
              <Link
                to={s.to}
                aria-current={current ? 'step' : undefined}
                data-state={current ? 'current' : s.done ? 'done' : 'open'}
                className={`${base} transition-colors ${current ? 'font-semibold text-link' : 'text-slate-700 hover:bg-slate-100'}`}
              >
                {current && (
                  <motion.span
                    layoutId="stepper-active"
                    className="absolute inset-0 rounded-full bg-sky-50 ring-1 ring-sky-400/40"
                    transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 380, damping: 32 }}
                  />
                )}
                {num}
                <span className="relative z-10">{s.label}</span>
              </Link>
            )}
          </li>
        )
      })}
    </ol>
  )
}
