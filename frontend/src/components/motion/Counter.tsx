import { animate, useInView, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'

/** Counts from 0 to `to` once it scrolls into view. Shows the final number under reduced motion. */
export function Counter({ to, className = '' }: { to: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-10% 0px' })
  const reduce = useReducedMotion()
  const [v, setV] = useState(reduce ? to : 0)
  useEffect(() => {
    if (reduce || !inView) return
    const c = animate(0, to, { duration: 1.2, ease: 'easeOut', onUpdate: (x) => setV(Math.round(x)) })
    return () => c.stop()
  }, [inView, to, reduce])
  return (
    <span ref={ref} className={className} data-final={to}>
      {reduce ? to : v}
    </span>
  )
}
