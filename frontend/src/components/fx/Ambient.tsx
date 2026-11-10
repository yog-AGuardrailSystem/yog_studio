import { motion, useScroll, useSpring, useTransform } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { m, useCalm } from '../../lib/motion'

/** Thin progress bar along the top edge: how far down the page you are. */
export function ScrollRail() {
  const { scrollYProgress } = useScroll()
  const scaleX = useSpring(scrollYProgress, { stiffness: 140, damping: 30 })
  return <motion.div aria-hidden className="fixed inset-x-0 top-0 z-30 h-0.5 origin-left bg-gradient-to-r from-sky-300 to-orange-400" style={{ scaleX }} {...m('fx:scroll-rail')} />
}

/** Section dots on the right edge; the current section's dot glows. Sections are found by [data-section]. */
export function SectionDots() {
  const [ids, setIds] = useState<string[]>([])
  const [active, setActive] = useState(0)
  useEffect(() => {
    const els = [...document.querySelectorAll<HTMLElement>('[data-section]')]
    setIds(els.map((e) => e.dataset.section!))
    const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && setActive(els.indexOf(e.target as HTMLElement))), { rootMargin: '-45% 0px -45% 0px' })
    els.forEach((e) => io.observe(e))
    return () => io.disconnect()
  }, [])
  if (!ids.length) return null
  return (
    <nav aria-label="Sections" className="fixed right-3 top-1/2 z-20 hidden -translate-y-1/2 flex-col gap-2 xl:flex">
      {ids.map((id, i) => (
        <a key={id} href={`#${id}`} aria-label={id} aria-current={i === active} {...m(`fx:dot:${i}`)}
          className={`h-2.5 w-2.5 rounded-full border border-sky-300 transition-all ${i === active ? 'scale-150 bg-sky-300 shadow-[0_0_10px_rgba(255,211,109,.9)]' : 'bg-transparent hover:bg-sky-300/50'}`} />
      ))}
    </nav>
  )
}

/** Drifting nodes joined by faint lines when close: a constellation behind the page. One canvas, throttled, paused off-screen. */
export function ParticleField() {
  const ref = useRef<HTMLCanvasElement>(null)
  const calm = useCalm()
  useEffect(() => {
    const cv = ref.current
    const ctx = cv?.getContext('2d')
    if (!cv || !ctx || calm) return
    let w = 0, h = 0, raf = 0, visible = true
    const pts = Array.from({ length: 46 }, () => ({ x: Math.random(), y: Math.random(), vx: (Math.random() - 0.5) * 0.00012, vy: (Math.random() - 0.5) * 0.00012 }))
    const resize = () => { w = cv.width = cv.clientWidth; h = cv.height = cv.clientHeight }
    resize()
    const ro = new ResizeObserver(resize); ro.observe(cv)
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) raf = requestAnimationFrame(tick) }); io.observe(cv)
    function tick() {
      if (!visible) return
      ctx!.clearRect(0, 0, w, h)
      for (const p of pts) { p.x = (p.x + p.vx * 16 + 1) % 1; p.y = (p.y + p.vy * 16 + 1) % 1 }
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i]
        ctx!.fillStyle = 'rgba(255,225,160,.6)'; ctx!.beginPath(); ctx!.arc(a.x * w, a.y * h, 1.6, 0, 7); ctx!.fill()
        for (let j = i + 1; j < pts.length; j++) {
          const b = pts[j], d = Math.hypot((a.x - b.x) * w, (a.y - b.y) * h)
          if (d < 130) { ctx!.strokeStyle = `rgba(245,185,66,${0.16 * (1 - d / 130)})`; ctx!.beginPath(); ctx!.moveTo(a.x * w, a.y * h); ctx!.lineTo(b.x * w, b.y * h); ctx!.stroke() }
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect() }
  }, [calm])
  return <canvas ref={ref} aria-hidden className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[110vh] w-full opacity-70" {...m('fx:particles')} />
}

/** A soft light that follows the pointer (desktop only). */
export function CursorGlow() {
  const calm = useCalm()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (calm || !window.matchMedia('(pointer: fine)').matches) return
    const move = (e: PointerEvent) => { if (ref.current) ref.current.style.transform = `translate(${e.clientX - 160}px, ${e.clientY - 160}px)` }
    window.addEventListener('pointermove', move, { passive: true })
    return () => window.removeEventListener('pointermove', move)
  }, [calm])
  if (calm) return null
  return <div ref={ref} aria-hidden className="pointer-events-none fixed left-0 top-0 z-0 h-80 w-80 rounded-full bg-sky-400/10 blur-3xl transition-transform duration-150 ease-out" {...m('fx:cursor-glow')} />
}

/** A ring that expands from every click. */
export function ClickRipple() {
  const calm = useCalm()
  useEffect(() => {
    if (calm) return
    const on = (e: PointerEvent) => {
      const d = document.createElement('span')
      d.className = 'click-ripple'; d.style.left = `${e.clientX}px`; d.style.top = `${e.clientY}px`; d.setAttribute('data-motion', 'fx:click-ripple')
      document.body.appendChild(d)
      setTimeout(() => d.remove(), 700)
    }
    window.addEventListener('pointerdown', on)
    return () => window.removeEventListener('pointerdown', on)
  }, [calm])
  return null
}

/** Text that scrambles into place the first time it scrolls into view. */
export function Scramble({ text, id }: { text: string; id: string }) {
  const calm = useCalm()
  const ref = useRef<HTMLSpanElement>(null)
  const [shown, setShown] = useState(text)
  useEffect(() => {
    const el = ref.current
    if (!el || calm) { setShown(text); return }
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return
      io.disconnect()
      let f = 0
      const t = setInterval(() => {
        f++
        setShown(text.split('').map((c, i) => (c === ' ' || i < f / 2 ? c : 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[Math.floor(Math.random() * 26)])).join(''))
        if (f / 2 >= text.length) { clearInterval(t); setShown(text) }
      }, 30)
    }, { threshold: 0.6 })
    io.observe(el)
    return () => io.disconnect()
  }, [text, calm])
  return <span ref={ref} aria-label={text} {...m(`fx:scramble:${id}`)}><span aria-hidden>{shown}</span></span>
}

/** A wrapper that leans toward the pointer. */
export function Magnetic({ children, id }: { children: ReactNode; id: string }) {
  const calm = useCalm()
  const ref = useRef<HTMLSpanElement>(null)
  return (
    <span ref={ref} className="inline-block transition-transform duration-150 ease-out" {...m(`fx:magnetic:${id}`)}
      onPointerMove={(e) => { if (calm || !ref.current) return; const r = ref.current.getBoundingClientRect(); ref.current.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * 0.18}px, ${(e.clientY - r.top - r.height / 2) * 0.25}px)` }}
      onPointerLeave={() => { if (ref.current) ref.current.style.transform = '' }}>
      {children}
    </span>
  )
}

/** Layers that drift at different speeds as you scroll. */
export function Parallax({ children, speed = 0.2, id }: { children: ReactNode; speed?: number; id: string }) {
  const calm = useCalm()
  const { scrollY } = useScroll()
  const y = useTransform(scrollY, [0, 1000], [0, -1000 * speed])
  return <motion.div style={calm ? undefined : { y }} {...m(`fx:parallax:${id}`)}>{children}</motion.div>
}

/** Second marquee: the YOG keywords and operators, scrolling the other way. */
export function KeywordMarquee() {
  const words = ['fact', 'rule', 'allow', 'deny', 'query', 'not', '==', '!=', '<', '>', '<=', '>=', '_', '#']
  const row = (
    <div className="marquee-track marquee-reverse" aria-hidden>
      {words.map((w, i) => <span key={i} className="whitespace-nowrap rounded border border-slate-700 bg-slate-900/60 px-3 py-1 font-mono text-sm text-emerald-200" {...m(`fx:kw:${i}`)}>{w}</span>)}
    </div>
  )
  return <div className="marquee" data-testid="keyword-marquee"><span className="sr-only">YOG keywords and operators: {words.join(' ')}</span>{row}{row}</div>
}
