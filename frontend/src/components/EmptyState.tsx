import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** A friendly "nothing here yet" card with one clear next action. */
export function EmptyState({ title, text, to, action }: { title: string; text: string; to?: string; action?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center" data-testid="empty-state">
      <p className="font-display text-lg font-bold">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">{text}</p>
      {to && action && (
        <Link to={to} className="btn-primary mt-4">
          {action}
        </Link>
      )}
    </div>
  )
}
