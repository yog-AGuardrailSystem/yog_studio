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
 * The interactive gold globe for the landing hero. Pointer: leans toward the cursor, parts around it, drag to spin,
 * dwell or click re-forms the logo. Stops drawing when off-screen or the tab is hidden; pause / reduced motion shows one still frame.
 */
export function HeroGlobeView({ className = '' }: { className?: string }) {
  const calm = useCalm()
  const ok = useMemo(() => webglOk(), [])
  const host = useRef<HTMLDivElement>(null)
  const input = useRef<GlobeInput>(newInput())
  const drag = useRef({ x: 0, y: 0, moved: 0 })
  const [onScreen, setOnScreen] = useState(true)
  const [tabVisible, setTabVisible] = useState(true)
  const n = useMemo(() => (window.innerWidth < 640 || window.matchMedia("(pointer: coarse)").matches ? 2400 : 5000), [])

  useEffect(() => {
    const el = host.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(([e]) => setOnScreen(e.isIntersecting))
    io.observe(el)
    const vis = () => setTabVisible(!document.hidden)
    document.addEventListener('visibilitychange', vis)
    return () => { io.disconnect(); document.removeEventListener('visibilitychange', vis) }
  }, [])

  const norm = (e: PointerEvent) => {
    const r = host.current!.getBoundingClientRect()
    return { x: ((e.clientX - r.left) / r.width) * 2 - 1, y: -(((e.clientY - r.top) / r.height) * 2 - 1), w: r.width, h: r.height }
  }
  const onMove = (e: PointerEvent) => {
    const p = norm(e), i = input.current
    i.x = p.x; i.y = p.y
    if (i.dragging) {
      i.dragDX += (e.clientX - drag.current.x) / p.w
      i.dragDY += (e.clientY - drag.current.y) / p.h
      drag.current.moved += Math.abs(e.clientX - drag.current.x) + Math.abs(e.clientY - drag.current.y)
      drag.current.x = e.clientX; drag.current.y = e.clientY
    }
  }
  const onEnter = (e: PointerEvent) => {
    const i = input.current
    const p = norm(e)
    i.x = p.x; i.y = p.y
    i.inside = true; i.enteredAt = performance.now() / 1000
  }
  const onLeave = () => { const i = input.current; i.inside = false; i.dragging = false }
  const onDown = (e: PointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, moved: 0 }
    input.current.dragging = true
    try { host.current?.setPointerCapture(e.pointerId) } catch { /* capture is a nicety */ }
  }
  const onUp = () => {
    const i = input.current
    if (i.dragging && drag.current.moved < 6) i.clickAt = performance.now() / 1000      // a tap or click, not a drag
    i.dragging = false
  }
  const showLogo = () => { input.current.clickAt = performance.now() / 1000 }

  return (
    <div className={`relative ${className}`}>
      <div ref={host} role="img" aria-label="An interactive globe of gold dots that forms the YOG logo"
        data-testid="hero-globe" data-calm={calm ? 'true' : 'false'} data-ready={ok ? undefined : 'fallback'}
        {...m('hero:globe')}
        className="absolute inset-x-0 top-0 bottom-14 cursor-grab select-none active:cursor-grabbing" style={{ touchAction: 'pan-y' }}
        onPointerMove={onMove} onPointerEnter={onEnter} onPointerLeave={onLeave} onPointerDown={onDown} onPointerUp={onUp} onPointerCancel={onLeave}>
        {ok ? (
          <Boundary fallback={<HeroLogoFallback />}>
            <Suspense fallback={null}>
              <HeroGlobe calm={calm} active={onScreen && tabVisible} n={n} input={input} host={host} />
            </Suspense>
          </Boundary>
        ) : <HeroLogoFallback />}
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col items-center gap-2 pb-1">
        <p className="text-xs text-slate-400" {...m('hero:globe-hint')}>Move your cursor, drag to spin, click to show the logo</p>
        <button type="button" onClick={showLogo} className="hero-logo-btn pointer-events-auto" data-testid="hero-logo-btn" {...m('hero:logo-btn')}>
          Show the logo
        </button>
      </div>
    </div>
  )
}
