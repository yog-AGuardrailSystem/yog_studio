import { Component, lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { HubState } from '../../lib/hubModel'
import type { HitsRef, UiRef } from './hubShared'

// three.js is only fetched when the hub is opened.
const HubScene = lazy(() => import('./HubScene'))

/** Like the shared error boundary, but tells the page so it can switch the buttons to plain tiles. */
class SceneBoundary extends Component<{ onFail: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch() { this.props.onFail() }
  render() { return this.state.failed ? null : this.props.children }
}

/** True for ~700 ms after `key` changes: calm mode only paints on demand, so it needs a moment of frames to show a new pose. */
function useBurst(key: string, ms = 700): boolean {
  const [on, setOn] = useState(true)
  useEffect(() => {
    setOn(true)
    const t = window.setTimeout(() => setOn(false), ms)
    return () => window.clearTimeout(t)
  }, [key, ms])
  return on
}

interface Props {
  state: HubState
  ui: UiRef
  hits: HitsRef
  calm: boolean
  /** Called once the scene has drawn its first frames. */
  onReady: () => void
  onFail: () => void
}

/** The 3D boxes, drawn behind the buttons. Stops drawing when scrolled off-screen or the tab is hidden. */
export function HubStageView({ state, ui, hits, calm, onReady, onFail }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const [onScreen, setOnScreen] = useState(true)
  const [tabVisible, setTabVisible] = useState(true)
  const small = useMemo(() => window.innerWidth < 720 || window.matchMedia('(pointer: coarse)').matches, [])
  const burst = useBurst(state.mode === 'rest' ? 'rest' : `${state.mode}:${state.group}:${'tool' in state ? state.tool : ''}`)
  // Calm mode and hover: show the new pose after the pointer moves between shapes.
  const [hoverKey, setHoverKey] = useState('')
  const hoverBurst = useBurst(hoverKey, 400)
  useEffect(() => {
    if (!calm) return
    const id = window.setInterval(() => {
      const k = `${ui.current.hoverBox ?? ''}|${ui.current.hoverCard ?? ''}`
      setHoverKey((p) => (p === k ? p : k))
    }, 120)
    return () => window.clearInterval(id)
  }, [calm, ui])

  useEffect(() => {
    const el = host.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(([e]) => setOnScreen(e.isIntersecting))
    io.observe(el)
    const vis = () => setTabVisible(!document.hidden)
    document.addEventListener('visibilitychange', vis)
    return () => { io.disconnect(); document.removeEventListener('visibilitychange', vis) }
  }, [])

  return (
    <div ref={host} className="absolute inset-0" aria-hidden data-testid="hub-canvas">
      <SceneBoundary onFail={onFail}>
        <Suspense fallback={null}>
          <HubScene state={state} ui={ui} hits={hits} calm={calm} active={onScreen && tabVisible} small={small} onReady={onReady} burst={burst || hoverBurst} />
        </Suspense>
      </SceneBoundary>
    </div>
  )
}
