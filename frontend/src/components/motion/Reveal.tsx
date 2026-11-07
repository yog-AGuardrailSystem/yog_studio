import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'

/** Fades/slides content in when it enters the viewport. Static under reduced motion. */
export function Reveal({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion()
  if (reduce) return <div className={className}>{children}</div>
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-10% 0px' }}
      transition={{ duration: 0.45, delay, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  )
}
