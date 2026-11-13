import { useEffect, useRef, type MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import { accentFor, boxLabel, cardIndex, toolsIn, type HubState } from '../../lib/hubModel'
import { GROUPS, TOOLS, type ToolGroup } from '../../lib/tools'
import type { HitsRef, UiRef } from './hubShared'

interface Props {
  state: HubState
  /** True when the 3D scene positions the buttons. False: they are drawn as plain tiles (no WebGL, or the scene failed). */
  projected: boolean
  hits: HitsRef
  ui: UiRef
  onOpen: (g: ToolGroup) => void
  onEnter: (toolId: string) => void
  onBack: () => void
  /** Called when the pointer or keyboard focus moves between shapes, so the label under the stage can change. */
  onHover: () => void
}

/** True when the user got to this element with the keyboard (a mouse click does not make focus visible). */
const keyboardFocus = (el: Element | null) => !!el && el instanceof HTMLElement && el.matches(':focus-visible')

const modified = (e: MouseEvent) => e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0

/** The interactive layer of the hub: the same five boxes and the open box's cards, as real buttons and links. */
export function HubOverlay({ state, projected, hits, ui, onOpen, onEnter, onBack, onHover }: Props) {
  const lastBox = useRef<ToolGroup | null>(null)
  const byKeyboard = useRef(false)                  // was the last input a key press (not a mouse or touch)?
  useEffect(() => {
    const key = () => { byKeyboard.current = true }
    const ptr = () => { byKeyboard.current = false }
    document.addEventListener('keydown', key, true)
    document.addEventListener('pointerdown', ptr, true)
    return () => { document.removeEventListener('keydown', key, true); document.removeEventListener('pointerdown', ptr, true) }
  }, [])
  const firstCard = useRef<HTMLAnchorElement | null>(null)
  const refFor = (key: string) => (el: HTMLElement | null) => {
    if (el) hits.current.set(key, el)
    else hits.current.delete(key)
  }
  const set = (patch: Partial<typeof ui.current>) => { Object.assign(ui.current, patch); onHover() }

  // Keyboard users: opening a box moves focus to its first card, closing it returns focus to the box they opened.
  // (keyed on the mode and group only: the state object is rebuilt on every render, and re-focusing would steal the hover.)
  const mode = state.mode === 'rest' ? 'rest' : 'box'
  const openGroup = state.mode === 'rest' ? null : state.group
  useEffect(() => {
    let raf = 0
    // The scene shows each button only once its 3D shape is on screen, and a hidden element cannot take focus: try for a moment.
    const focusWhenShown = (get: () => HTMLElement | null | undefined, left: number) => {
      const el = get()
      el?.focus({ preventScroll: true })
      if (el && document.activeElement !== el && left > 0) raf = requestAnimationFrame(() => focusWhenShown(get, left - 1))
    }
    if (mode === 'box') {
      lastBox.current = openGroup
      if (byKeyboard.current) focusWhenShown(() => firstCard.current, 90)
    } else if (lastBox.current) {
      const back = lastBox.current
      lastBox.current = null
      if (byKeyboard.current && (!document.activeElement || document.activeElement === document.body)) focusWhenShown(() => hits.current.get(`box:${back}`), 90)
    }
    return () => cancelAnimationFrame(raf)
  }, [mode, openGroup, hits])

  const cls = projected ? 'hub-hit' : 'hub-tile'

  if (state.mode === 'rest') {
    return (
      <div className={projected ? 'absolute inset-0' : 'hub-tiles'} data-testid="hub-boxes">
        {GROUPS.map((g) => {
          const { title, count } = boxLabel(g.id)
          return (
            <button key={g.id} ref={refFor(`box:${g.id}`)} type="button" className={cls} data-testid={`box-${g.id}`}
              aria-label={`${title}: ${count} tools. Open this box.`}
              onClick={() => onOpen(g.id)}
              onPointerEnter={() => set({ hoverBox: g.id })} onPointerLeave={() => set({ hoverBox: null })}
              onFocus={(e) => { if (keyboardFocus(e.currentTarget)) set({ hoverBox: g.id }) }} onBlur={() => set({ hoverBox: null })}>
              {!projected && (<><span className="hub-tile-title">{title}</span><span className="hub-tile-count">{count} tools</span></>)}
            </button>
          )
        })}
      </div>
    )
  }

  const group = state.group
  const tools = toolsIn(group)
  return (
    <div className={projected ? 'absolute inset-0' : 'hub-tiles'} data-testid="hub-cards">
      <button type="button" className="hub-back" data-testid="hub-back" onClick={onBack}>
        <span aria-hidden>←</span> All boxes
      </button>
      {tools.map((t, i) => (
        <Link key={t.id} to={t.to} ref={(el) => { refFor(`card:${t.id}`)(el); if (i === 0) firstCard.current = el }}
          className={cls} data-testid={`card-open-${t.id}`} style={{ ['--accent' as string]: accentFor(t.id) }}
          aria-label={`${cardIndex(group, t.id)} ${t.name}: ${t.purpose}`}
          onClick={(e) => { if (modified(e)) return; e.preventDefault(); onEnter(t.id) }}
          onPointerEnter={() => set({ hoverCard: t.id })} onPointerLeave={() => set({ hoverCard: null })}
          onFocus={(e) => { if (keyboardFocus(e.currentTarget)) set({ hoverCard: t.id }) }} onBlur={() => set({ hoverCard: null })}>
          {!projected && (<><span className="hub-tile-count">{cardIndex(group, t.id)}</span><span className="hub-tile-title">{t.name}</span></>)}
        </Link>
      ))}
    </div>
  )
}

/** The line under the stage: names the box or card the pointer is on, or tells you what to do. */
export function hubCaption(state: HubState, hoverBox: ToolGroup | null, hoverCard: string | null) {
  if (state.mode === 'rest') {
    if (hoverBox) {
      const { title, count } = boxLabel(hoverBox)
      return { lead: title, text: `${count} tools. ${GROUPS.find((g) => g.id === hoverBox)!.blurb}`, color: null as string | null }
    }
    return { lead: 'Pick a box', text: 'Each one holds the tools for one stage.', color: null }
  }
  if (hoverCard) {
    const t = TOOLS.find((x) => x.id === hoverCard)!
    return { lead: `${cardIndex(state.group, t.id)}  ${t.name} ↗`, text: t.purpose, color: accentFor(t.id) }
  }
  const g = GROUPS.find((x) => x.id === state.group)!
  return { lead: g.title, text: g.blurb, color: null }
}
