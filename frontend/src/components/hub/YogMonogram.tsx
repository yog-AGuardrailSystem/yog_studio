import { useEffect, useId, useRef, useState } from 'react'
import { useCalm } from '../../lib/motion'
import { revealProgress } from '../../lib/scramble'
import { GROUPS } from '../../lib/tools'
import { Scrambled } from './Scrambled'

const HEADLINE = 'A rulebook your AI agent can’t break.'
const P1 = 'YOG is a small policy language and engine. Every action an AI agent wants to take gets one answer, ALLOW or DENY, the same every time, with the reason.'
const P2 = 'Studio is the toolkit around it. Upload your agent, write the rules in plain English, let an AI draft the policy and let the engine check it. Nothing goes live until you approve it, and DENY always beats ALLOW.'

/** A halftone "YOG": gold dots on black whose size follows the letter shapes, swept in from the left. */
function HalftoneMark({ run }: { run: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const calm = useCalm()
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const W = 240, H = 150, STEP = 6
    cv.width = W; cv.height = H
    const ctx = cv.getContext('2d')
    if (!ctx) return
    const off = document.createElement('canvas')
    off.width = W; off.height = H
    const o = off.getContext('2d')
    if (!o) return
    o.fillStyle = '#000'; o.fillRect(0, 0, W, H)
    o.fillStyle = '#fff'; o.font = '800 118px "Inter Tight", Inter, system-ui, sans-serif'
    o.textAlign = 'center'; o.textBaseline = 'middle'
    o.fillText('YOG', W / 2, H / 2 + 6)
    const px = o.getImageData(0, 0, W, H).data
    const dots: { x: number; y: number; r: number; jitter: number }[] = []
    for (let y = STEP / 2; y < H; y += STEP) for (let x = STEP / 2; x < W; x += STEP) {
      let s = 0
      for (let dy = -2; dy <= 2; dy += 2) for (let dx = -2; dx <= 2; dx += 2) s += px[((Math.floor(y) + dy) * W + Math.floor(x) + dx) * 4]
      const lum = s / 9 / 255
      dots.push({ x, y, r: 0.5 + lum * 2.6, jitter: Math.random() * 0.25 })
    }
    const draw = (p: number) => {
      ctx.clearRect(0, 0, W, H)
      ctx.fillStyle = '#f5b942'
      for (const d of dots) {
        const local = Math.min(1, Math.max(0, (p * 1.25 - d.x / W) / 0.25 - d.jitter))
        if (local <= 0) continue
        ctx.beginPath(); ctx.arc(d.x, d.y, d.r * local, 0, Math.PI * 2); ctx.fill()
      }
    }
    if (calm) { draw(1); return }
    if (!run) { draw(0); return }
    let raf = 0
    const t0 = performance.now()
    const tick = () => {
      const p = revealProgress(performance.now() - t0, 80, 900)
      draw(p)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [run, calm])
  return <canvas ref={ref} aria-hidden className="hub-about-mark" />
}

/**
 * Top-left "YOG". Hover (after a short pause), keyboard focus or a tap opens the About panel; the scene behind it slides aside
 * (the parent reads `onOpenChange`). Escape or moving away closes it. Everything in the panel is also on the How it works page.
 */
export function YogMonogram({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  const [open, setOpen] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  const panelId = useId()
  const apply = (v: boolean) => { setOpen(v); onOpenChange(v) }
  const later = (v: boolean, ms: number) => { window.clearTimeout(timer.current); timer.current = window.setTimeout(() => apply(v), ms) }
  useEffect(() => () => window.clearTimeout(timer.current), [])
  useEffect(() => {
    if (!open) return
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') apply(false) }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  })

  return (
    <div className="hub-yog" onPointerEnter={(e) => { if (e.pointerType === 'mouse') later(true, 120) }}
      onPointerLeave={(e) => { if (e.pointerType === 'mouse') later(false, 260) }}>
      <button type="button" data-testid="yog-monogram" className="hub-yog-btn" aria-expanded={open} aria-controls={panelId}
        onClick={() => { window.clearTimeout(timer.current); apply(!open) }}
        onFocus={() => later(true, 0)} onBlur={(e) => { if (!e.currentTarget.parentElement?.contains(e.relatedTarget as Node)) later(false, 0) }}>
        <span className="hub-yog-mark">{open ? 'YOG Studio' : 'YOG'}</span>
      </button>
      <section id={panelId} data-testid="yog-about" aria-label="About YOG Studio" hidden={!open} className="hub-about">
        <HalftoneMark run={open} />
        <h2 className="hub-about-head"><Scrambled text={HEADLINE} run={open} delay={120} duration={700} /></h2>
        <p className="hub-about-p"><Scrambled text={P1} run={open} delay={420} duration={900} /></p>
        <p className="hub-about-p hub-about-p2"><Scrambled text={P2} run={open} delay={700} duration={1000} /></p>
        <ul className="hub-about-chips" aria-label="The five stages">
          {GROUPS.map((g, i) => <li key={g.id}><span>{String(i + 1).padStart(2, '0')}</span> {g.title}</li>)}
        </ul>
      </section>
    </div>
  )
}
