import { MotionConfig, useReducedMotion } from 'motion/react'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

/**
 * Motion system.
 *  - `m(id)` tags an element as one registered motion behaviour (docs/motion-inventory.md, e2e/motion.mjs counts them).
 *  - The user can pause all motion (header button); the OS "reduce motion" setting does the same automatically.
 *  - `useCalm()` is what custom animation code asks before moving anything.
 */
export const m = (id: string) => ({ 'data-motion': id }) as const

const KEY = 'yog.motion'
interface Ctx { paused: boolean; setPaused: (p: boolean) => void }
const MotionCtx = createContext<Ctx>({ paused: false, setPaused: () => undefined })

function readPref(): boolean {
  try { return localStorage.getItem(KEY) === 'paused' } catch { return false }
}

export function MotionProvider({ children }: { children: ReactNode }) {
  const [paused, setPausedState] = useState(readPref)
  useEffect(() => {
    document.documentElement.dataset.motion = paused ? 'paused' : 'on'
    try { localStorage.setItem(KEY, paused ? 'paused' : 'on') } catch { /* preference only */ }
  }, [paused])
  return (
    <MotionCtx.Provider value={{ paused, setPaused: setPausedState }}>
      <MotionConfig reducedMotion={paused ? 'always' : 'user'}>{children}</MotionConfig>
    </MotionCtx.Provider>
  )
}

export const useMotionPref = () => useContext(MotionCtx)

/** True when nothing should move: the user paused motion, or the OS asks for reduced motion. */
export function useCalm(): boolean {
  const os = useReducedMotion()
  const { paused } = useContext(MotionCtx)
  return !!os || paused
}

export function MotionToggle({ className = '' }: { className?: string }) {
  const { paused, setPaused } = useMotionPref()
  return (
    <button type="button" className={`motion-toggle ${className}`} aria-pressed={paused} onClick={() => setPaused(!paused)} data-testid="motion-toggle"
      title="Pause or resume all animation on this site">
      <span aria-hidden>{paused ? '▶' : '⏸'}</span>
      <span className="hidden sm:inline"> {paused ? 'Motion off' : 'Motion on'}</span>
      <span className="sr-only sm:hidden">{paused ? 'Motion is off. Turn on' : 'Motion is on. Turn off'}</span>
    </button>
  )
}
