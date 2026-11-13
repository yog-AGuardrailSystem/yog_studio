import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { captionFor, hashFor, hubReducer, parseHash, type HubState } from '../../lib/hubModel'
import { m, MotionToggle, useCalm } from '../../lib/motion'
import { TOOLS, type ToolGroup } from '../../lib/tools'
import { webglOk } from '../three/webgl'
import './hub.css'
import { HubStageView } from './HubStageView'
import { ENTER_MS, newUi, type HitMap } from './hubShared'
import { HubOverlay } from './HubOverlay'
import { Scrambled } from './Scrambled'
import { YogMonogram } from './YogMonogram'

/**
 * The top of /studio: five boxes in 3D. Click one and it opens to show its tools as cards; click a card to open the tool.
 * The 3D scene only draws. The buttons and links are real elements over it, so keyboard, touch and screen readers work,
 * and with no WebGL the same flow runs on plain tiles. `status` (tool count, approved policy) sits bottom right.
 */
export function HubSection({ status }: { status: ReactNode }) {
  const { hash, key } = useLocation()
  const navigate = useNavigate()
  const calm = useCalm()
  const ui = useRef(newUi())
  const hits = useRef<HitMap>(new Map())
  const pushed = useRef(false)                       // did this page push the "box open" history entry?
  const [entering, setEntering] = useState<string | null>(null)
  const [aside, setAside] = useState(false)
  const [failed, setFailed] = useState(false)
  const [ready, setReady] = useState(false)
  const [, setTick] = useState(0)
  const projected = useMemo(() => webglOk(), []) && !failed

  const base = parseHash(hash)
  const state: HubState = entering && base.mode === 'box' ? hubReducer(base, { type: 'enter', tool: entering }) : base

  // Any navigation ends a card's flight. While a tool page is still loading, React keeps showing this page (the router
  // navigates inside a transition, so this instance never sees the new location). Pressing Back in that moment returns to
  // this same instance, which must not stay frozen mid-flight: the browser's popstate tells us. The pending jump is cancelled.
  const flight = useRef<number | undefined>(undefined)
  useEffect(() => {
    setEntering(null)
    const reset = () => { window.clearTimeout(flight.current); setEntering(null) }
    window.addEventListener('popstate', reset)
    return () => { window.removeEventListener('popstate', reset); window.clearTimeout(flight.current) }
  }, [key])

  const open = useCallback((g: ToolGroup) => { pushed.current = true; navigate({ hash: hashFor({ mode: 'box', group: g }) }) }, [navigate])
  const back = useCallback(() => {
    if (pushed.current) { pushed.current = false; navigate(-1) } else navigate({ hash: '' }, { replace: true })
  }, [navigate])
  const enter = useCallback((id: string) => {
    const t = TOOLS.find((x) => x.id === id)
    if (!t) return
    setEntering(id)
    window.clearTimeout(flight.current)
    flight.current = window.setTimeout(() => navigate(t.to), calm ? 0 : ENTER_MS)
  }, [navigate, calm])

  useEffect(() => {
    if (state.mode !== 'box') return
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape' && !aside) back() }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [state.mode, aside, back])

  const cap = captionFor(state, ui.current.hoverBox, ui.current.hoverCard)
  const onHover = useCallback(() => setTick((n) => n + 1), [])
  const onReady = useCallback(() => setReady(true), [])
  const onFail = useCallback(() => setFailed(true), [])

  return (
    <section className="hub-stage" data-testid="hub-stage" aria-labelledby="hub-title" data-state={state.mode}
      data-ready={ready ? 'scene' : projected ? 'loading' : 'fallback'} {...m('hub:stage')}>
      <h1 id="hub-title" className="sr-only">Studio: five stages, {TOOLS.length} tools</h1>

      <div className="hub-world" data-aside={aside ? 'true' : 'false'} data-entering={state.mode === 'enter' ? 'true' : 'false'}>
        {projected && <HubStageView state={state} ui={ui} hits={hits} calm={calm} onReady={onReady} onFail={onFail} />}
        <HubOverlay state={state} projected={projected} hits={hits} ui={ui} onOpen={open} onEnter={enter} onBack={back} onHover={onHover} />
      </div>

      <YogMonogram onOpenChange={setAside} />

      <nav className="hub-nav" aria-label="Site">
        <Link to="/" className="hub-nav-link hidden sm:inline">Home</Link>
        <Link to="/how-it-works" className="hub-nav-link">How it works</Link>
        <MotionToggle />
      </nav>

      <div className="hub-caption" aria-live="polite" data-testid="hub-caption" data-aside={aside ? 'true' : 'false'}>
        <p className="hub-caption-lead" style={cap.color ? { color: cap.color } : undefined}>
          {cap.index && <span className="hub-caption-index">{cap.index}</span>}
          <span className="hub-caption-name"><Scrambled key={cap.name} text={cap.name} /></span>
          {cap.arrow && <span className="hub-caption-arrow" aria-hidden>↗</span>}
        </p>
        <p className="hub-caption-text">{cap.text}</p>
      </div>

      <div className="hub-status">{status}</div>
      <a href="#all-tools" className="hub-scroll" data-testid="hub-scroll">All {TOOLS.length} tools explained <span aria-hidden>↓</span></a>
      <div className="hub-fade" data-testid="hub-fade" data-on={state.mode === 'enter' ? 'true' : 'false'} aria-hidden />
    </section>
  )
}
