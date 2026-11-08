import { Component, lazy, Suspense, useMemo, type ReactNode } from 'react'
import { useReducedMotion } from 'motion/react'
import type { GateSceneProps } from './GateScene'

// three.js lives in its own chunk and only loads on pages that render <Gate/> (never in Studio).
const GateScene = lazy(() => import('./GateScene'))

function webglOk(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('fx') === 'off') return false
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

class Boundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

/**
 * Lazy 3D scene with graceful fallbacks: no WebGL / ?fx=off / render error -> `fallback`.
 * Reduced motion -> one still frame (no loop, no autoplay).
 */
export function Gate({ fallback, className = '', ...props }: GateSceneProps & { fallback: ReactNode }) {
  const reduce = useReducedMotion()
  const ok = useMemo(webglOk, [])
  if (!ok) return <div data-testid="gate-fallback" className={className}>{fallback}</div>
  return (
    <Boundary fallback={<div data-testid="gate-fallback" className={className}>{fallback}</div>}>
      <Suspense fallback={<div className={`gate-skeleton ${className}`} aria-hidden />}>
        <GateScene {...props} className={className} still={!!reduce || props.still} autoplay={!reduce && props.autoplay !== false} />
      </Suspense>
    </Boundary>
  )
}
