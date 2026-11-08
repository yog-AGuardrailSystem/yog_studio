import { motion, useReducedMotion } from 'motion/react'

const N = 20
/** One-shot burst of dots (e.g. when a policy is approved). Mount it with a new `key` to replay. */
export function Burst({ colors = ['#22c55e', '#38bdf8', '#86efac', '#7dd3fc'] }: { colors?: string[] }) {
  const reduce = useReducedMotion()
  if (reduce) return null
  return (
    <span className="pointer-events-none absolute left-0 top-1/2 h-0 w-0" aria-hidden data-testid="burst">
      {Array.from({ length: N }, (_, i) => {
        const a = (i / N) * Math.PI * 2
        const d = 50 + (i % 4) * 22
        return (
          <motion.span
            key={i}
            className="absolute h-1.5 w-1.5 rounded-full"
            style={{ background: colors[i % colors.length], boxShadow: `0 0 8px ${colors[i % colors.length]}` }}
            initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
            animate={{ x: Math.cos(a) * d, y: Math.sin(a) * d, opacity: 0, scale: 0.3 }}
            transition={{ duration: 0.9, ease: 'easeOut' }}
          />
        )
      })}
    </span>
  )
}
