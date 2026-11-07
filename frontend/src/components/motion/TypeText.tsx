import { useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'

/** Types `text` out once `run` is true. Shows the full text immediately under reduced motion. */
export function TypeText({ text, run, speed = 28, onDone }: { text: string; run: boolean; speed?: number; onDone?: () => void }) {
  const reduce = useReducedMotion()
  const [n, setN] = useState(0)
  useEffect(() => {
    if (reduce) return
    if (!run) {
      setN(0)
      return
    }
    setN(0)
    let i = 0
    const id = setInterval(() => {
      i += 1
      setN(i)
      if (i >= text.length) {
        clearInterval(id)
        onDone?.()
      }
    }, speed)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, text, speed, reduce])
  const shown = reduce ? text : text.slice(0, n)
  return (
    <span aria-label={text}>
      <span aria-hidden>{shown}</span>
    </span>
  )
}
