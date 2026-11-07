import type { ReactNode } from 'react'

/** One idea per screen: a heading first, then content, on equal left/right edges. */
export function Section({
  id,
  eyebrow,
  title,
  children,
  tone = 'light',
}: {
  id?: string
  eyebrow?: string
  title: string
  children: ReactNode
  tone?: 'light' | 'muted' | 'dark'
}) {
  const bg = tone === 'dark' ? 'bg-slate-950 text-white' : tone === 'muted' ? 'bg-slate-50' : 'bg-white'
  return (
    <section id={id} className={`${bg} flex min-h-[70vh] items-center py-16 sm:py-20`}>
      <div className="mx-auto w-full max-w-6xl px-5">
        {eyebrow && <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-brand">{eyebrow}</p>}
        <h2 className="font-display max-w-3xl text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{title}</h2>
        <div className="mt-8">{children}</div>
      </div>
    </section>
  )
}
