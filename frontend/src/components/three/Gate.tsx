import { lazy, Suspense, useMemo, type ReactNode } from 'react'
import { useReducedMotion } from 'motion/react'
import type { GateSceneProps } from './GateScene'
import { Boundary, webglOk } from './webgl'

// three.js lives in its own chunk and only loads on pages that render <Gate/> (never in Studio).
const GateScene = lazy(() => import('./GateScene'))

/**
 * Lazy 3D scene with graceful fallbacks: no WebGL / ?fx=off / render error -> `fallback`.
 * Reduced motion -> one still frame (no loop, no autoplay).
 */
export function Gate({ fallback, className = '', ...props }: GateSceneProps & { fallback: ReactNode }) {
  const reduce = useReducedMotion()
  const ok = useMemo(() => webglOk(), [])
  if (!ok) return <div data-testid="gate-fallback" className={className}>{fallback}</div>
  return (
    <Boundary fallback={<div data-testid="gate-fallback" className={className}>{fallback}</div>}>
      <Suspense fallback={<div className={`gate-skeleton ${className}`} aria-hidden />}>
        <GateScene {...props} className={className} still={!!reduce || props.still} autoplay={!reduce && props.autoplay !== false} />
      </Suspense>
    </Boundary>
  )
}
