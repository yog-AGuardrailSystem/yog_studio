import type { ReactNode } from 'react'

/** Glass card whose glow follows the cursor (CSS vars --mx/--my). Touch devices just get the static card. */
export function Spotlight({ children, className = '', as: Tag = 'div' }: { children: ReactNode; className?: string; as?: 'div' | 'li' }) {
  return (
    <Tag
      className={`glass spot ${className}`}
      onPointerMove={(e: React.PointerEvent<HTMLElement>) => {
        const el = e.currentTarget
        const r = el.getBoundingClientRect()
        el.style.setProperty('--mx', `${e.clientX - r.left}px`)
        el.style.setProperty('--my', `${e.clientY - r.top}px`)
      }}
    >
      {children}
    </Tag>
  )
}
