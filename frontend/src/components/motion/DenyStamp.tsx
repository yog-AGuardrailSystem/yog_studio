import { motion, useReducedMotion } from 'motion/react'

/** ALLOW / DENY stamp that slams in. `id` changes replay it. Under reduced motion it just appears. */
export function DenyStamp({ decision, id }: { decision: 'ALLOW' | 'DENY'; id: number | string }) {
  const reduce = useReducedMotion()
  const deny = decision === 'DENY'
  const cls = deny ? 'border-red-600 bg-red-50 text-red-700' : 'border-emerald-600 bg-emerald-50 text-emerald-700'
  return (
    <motion.span
      key={id}
      data-testid="stamp"
      data-decision={decision}
      className={`font-display inline-block rounded-md border-4 px-4 py-1 text-3xl font-extrabold tracking-wider ${cls}`}
      initial={reduce ? false : { scale: 2.2, opacity: 0, rotate: deny ? -8 : 0 }}
      animate={{ scale: 1, opacity: 1, rotate: deny ? -4 : 0 }}
      transition={{ type: 'spring', stiffness: 500, damping: 22 }}
    >
      {decision}
    </motion.span>
  )
}
