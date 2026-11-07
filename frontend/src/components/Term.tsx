import type { ReactNode } from 'react'

/** Jargon word with a hover/focus explanation. Keyboard reachable. */
export function Term({ children, tip }: { children: ReactNode; tip: string }) {
  return (
    <span className="term" tabIndex={0}>
      {children}
      <span role="tooltip" className="term-tip">
        {tip}
      </span>
    </span>
  )
}
