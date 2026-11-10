import { lazy, Suspense, useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { m, useCalm } from '../../lib/motion'
import { newInput, type GlobeInput } from './globeInput'
import { Boundary, webglOk } from './webgl'

// three.js lives in its own chunk, loaded only by pages that show the globe.
const HeroGlobe = lazy(() => import('./HeroGlobe'))

/** No WebGL, ?fx=off or a render error: a static gold wordmark inside a dotted ring. */
function HeroLogoFallback() {
  return <div className="hero-logo-fallback" data-testid="hero-globe-fallback" aria-hidden><span>YOG</span></div>
}

/**
 * The interactive gold orb for the landing hero, with the YOG logo living inside it.
 * Drag to turn it (it coasts), hover to nudge a few dots, click for a ripple and a burst of dots.
 * Stops drawing when off-screen or the tab is hidden; pause / reduced motion shows one still frame facing the viewer.
 */
export function HeroGlobeView({ className = '' }: { className?: string }) {
  const calm = useCalm()
  const ok = useMemo(() => webglOk(), [])
  const host = useRef<HTMLDivElement>(null)
  const input = useRef<GlobeInput>(newInput())
  const drag = useRef({ x: 0, y: 0, moved: 0 })
  const [onScreen, setOnScreen] = useState(true)
  const [tabVisible, setTabVisible] = useState(true)
  const small = useMemo(() => window.innerWidth < 640 || window.matchMedia('(pointer: coarse)').matches, [])
  const nOrb = small ? 7000 : 14000
  const nLogo = small ? 4200 : 9000

  useEffect(() => {
    const el = host.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(([e]) => setOnScreen(e.isIntersecting))
    io.observe(el)
    const vis = () => setTabVisible(!document.hidden)
    document.addEventListener('visibilitychange', vis)
    return () => { io.disconnect(); document.removeEventListener('visibilitychange', vis) }
  }, [])

  const local = (e: PointerEvent) => {
    const r = host.current!.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }
  const onMove = (e: PointerEvent) => {
    const i = input.current, p = local(e)
    i.x = p.x; i.y = p.y
    if (i.dragging) {
      i.dragDX += e.clientX - drag.current.x
      i.dragDY += e.clientY - drag.current.y
      drag.current.moved += Math.abs(e.clientX - drag.current.x) + Math.abs(e.clientY - drag.current.y)
      drag.current.x = e.clientX; drag.current.y = e.clientY
    }
  }
  const onEnter = (e: PointerEvent) => { const i = input.current, p = local(e); i.x = p.x; i.y = p.y; i.inside = true }
  const onLeave = () => { const i = input.current; i.inside = false; i.dragging = false; i.x = -1e4; i.y = -1e4 }
  const onDown = (e: PointerEvent) => {
    if (e.button !== 0) return                                   // the secondary button never starts a drag
    drag.current = { x: e.clientX, y: e.clientY, moved: 0 }
    input.current.dragging = true
    try { host.current?.setPointerCapture(e.pointerId) } catch { /* capture is a nicety */ }
  }
  const onUp = (e: PointerEvent) => {
    const i = input.current
    if (i.dragging && drag.current.moved < 6) { const p = local(e); i.clickX = p.x; i.clickY = p.y; i.clickId++ }   // a click/tap, not a drag
    i.dragging = false
  }

  return (
    <div className={`relative ${className}`}>
      <div ref={host} role="img" aria-label="An interactive globe of gold dots with the YOG logo inside it"
        data-testid="hero-globe" data-calm={calm ? 'true' : 'false'} data-ready={ok ? undefined : 'fallback'}
        {...m('hero:globe')}
        className="absolute inset-0 cursor-grab select-none active:cursor-grabbing" style={{ touchAction: 'pan-y' }}
        onPointerMove={onMove} onPointerEnter={onEnter} onPointerLeave={onLeave} onPointerDown={onDown} onPointerUp={onUp} onPointerCancel={onLeave}>
        {ok ? (
          <Boundary fallback={<HeroLogoFallback />}>
            <Suspense fallback={null}>
              <HeroGlobe calm={calm} active={onScreen && tabVisible} nOrb={nOrb} nLogo={nLogo} input={input} host={host} />
            </Suspense>
          </Boundary>
        ) : <HeroLogoFallback />}
      </div>
    </div>
  )
}
