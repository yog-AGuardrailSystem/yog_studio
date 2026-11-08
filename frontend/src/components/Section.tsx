import type { ReactNode } from 'react'
import { Reveal } from './motion/Reveal'

/** One idea per screen: a heading first, then content, on equal left/right edges. Dark ground. */
export function Section({
  id,
  eyebrow,
  title,
  children,
  band = false,
}: {
  id?: string
  eyebrow?: string
  title: ReactNode
  children: ReactNode
  /** subtle darker band to separate sections */
  band?: boolean
}) {
  return (
    <section id={id} className={`${band ? 'bg-black/25' : ''} flex min-h-[70vh] items-center py-16 sm:py-24`}>
      <div className="mx-auto w-full max-w-6xl px-5">
        <Reveal>
          {eyebrow && <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-glow">{eyebrow}</p>}
          <h2 className="font-display max-w-3xl text-3xl font-bold leading-tight tracking-tight sm:text-5xl">{title}</h2>
        </Reveal>
        <div className="mt-10">{children}</div>
      </div>
    </section>
  )
}
