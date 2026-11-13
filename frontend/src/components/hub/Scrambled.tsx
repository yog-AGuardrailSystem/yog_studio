import { useEffect, useState } from 'react'
import { useCalm } from '../../lib/motion'
import { revealProgress, scrambleFrame } from '../../lib/scramble'

/** Text that builds in with a scramble (left to right, random glyphs just ahead) whenever `run` is true and whenever the text
 *  changes. Calm motion: simply the text. */
export function useScramble(text: string, run: boolean, delay: number, duration: number): string {
  const calm = useCalm()
  const [out, setOut] = useState(calm ? text : scrambleFrame(text, 0))
  useEffect(() => {
    if (calm) { setOut(text); return }
    if (!run) { setOut(scrambleFrame(text, 0)); return }
    let raf = 0
    const t0 = performance.now()
    const tick = () => {
      const p = revealProgress(performance.now() - t0, delay, duration)
      setOut(scrambleFrame(text, p))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [text, run, delay, duration, calm])
  return out
}

/** The scrambling text for the eye, and the real text for screen readers (they never hear the flicker). */
export function Scrambled({ text, run = true, delay = 0, duration = 420 }: { text: string; run?: boolean; delay?: number; duration?: number }) {
  const shown = useScramble(text, run, delay, duration)
  return (<><span aria-hidden>{shown}</span><span className="sr-only">{text}</span></>)
}
