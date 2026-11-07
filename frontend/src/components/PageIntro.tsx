import type { ReactNode } from 'react'

/** One line saying what this screen is for and what to do on it. */
export function PageIntro({ step, title, children }: { step?: string; title: string; children: ReactNode }) {
  return (
    <div className="mb-5" data-testid="page-intro">
      {step && <p className="text-xs font-semibold uppercase tracking-widest text-brand">{step}</p>}
      <h1 className="font-display text-2xl font-bold tracking-tight">{title}</h1>
      <p className="mt-1 max-w-3xl text-sm text-slate-600">{children}</p>
    </div>
  )
}
