import { Link, useLocation } from 'react-router-dom'
import { useAppState } from '../state'

interface Step {
  to: string
  label: string
  done: boolean
  /** why it can't be opened yet; undefined = open */
  locked?: string
}

/** The Studio flow as a real stepper: current / done / locked, clickable when open. */
export function Stepper() {
  const { analysis, draft, approved } = useAppState()
  const { pathname } = useLocation()

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
        const base = 'inline-flex items-center gap-2 rounded-full px-3 py-1 transition-colors'
        const num = (
          <span
            className={`flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${
              s.done ? 'bg-emerald-600 text-white' : current ? 'bg-sky-700 text-white' : 'bg-slate-200 text-slate-600'
            }`}
            aria-hidden
          >
            {s.done ? '✓' : i + 1}
          </span>
        )
        return (
          <li key={s.to} className="flex items-center gap-1">
            {i > 0 && <span className="h-px w-3 bg-slate-300" aria-hidden />}
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
                className={`${base} ${current ? 'bg-sky-50 font-semibold text-sky-800' : 'text-slate-700 hover:bg-slate-100'}`}
              >
                {num}
                {s.label}
              </Link>
            )}
          </li>
        )
      })}
    </ol>
  )
}
