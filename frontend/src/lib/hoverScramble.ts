// Every button and link scrambles its text when the pointer (or keyboard focus) arrives, then settles back on the exact
// original, like the labels in the reference. One delegated listener for the whole site, installed once in main.tsx.
//
// The core (`ScrambleRun`) is pure and works on text accessors, so it is unit-tested without a browser. The DOM part
// only finds the text nodes and keeps things accessible and safe next to React.
import { GLYPHS, revealProgress, scrambleFrame } from './scramble.ts'

export const SCRAMBLE_MS = 380
const MAX_CHARS = 60

/** Something that holds text: a DOM text node in the browser, a plain object in tests. */
export interface TextSlot { get(): string; set(v: string): void }

/** One scramble of a set of text slots. `step(now)` writes the next frame; it returns true when the run is over. If anything
 *  else changed a slot's text meanwhile (React re-rendered it), the run stops and leaves that new text alone. */
export class ScrambleRun {
  private readonly slots: TextSlot[]
  private readonly duration: number
  private readonly rand: () => number
  private readonly originals: string[]
  private readonly written: string[]
  private readonly start: number
  stopped = false

  constructor(slots: TextSlot[], now: number, duration = SCRAMBLE_MS, rand: () => number = Math.random) {
    this.slots = slots
    this.duration = duration
    this.rand = rand
    this.originals = slots.map((s) => s.get())
    this.written = [...this.originals]
    this.start = now
  }

  step(now: number): boolean {
    if (this.stopped) return true
    // someone else changed the text: stop, and do not restore our (now stale) copy
    if (this.slots.some((s, i) => s.get() !== this.written[i])) { this.stopped = true; return true }
    const p = revealProgress(now - this.start, 0, this.duration)
    this.slots.forEach((s, i) => {
      const v = p >= 1 ? this.originals[i] : scrambleWithLead(this.originals[i], p, this.rand)
      if (v !== this.written[i]) { s.set(v); this.written[i] = v }
    })
    return p >= 1
  }

  /** Puts the original text back at once (when motion is switched off mid-run). */
  finish() {
    if (this.stopped) return
    this.slots.forEach((s, i) => { if (s.get() === this.written[i] && this.written[i] !== this.originals[i]) s.set(this.originals[i]) })
    this.stopped = true
  }

  get text(): string { return this.originals.join('') }
}

/** Unlike the About panel's build-in, a hover never blanks the label: unrevealed letters show glyphs, not spaces. */
export function scrambleWithLead(text: string, progress: number, rand: () => number): string {
  const f = scrambleFrame(text, progress, rand, text.length)
  return f.replace(/ /g, () => GLYPHS[Math.floor(rand() * GLYPHS.length)])
}

/** Whether a label is worth scrambling: some letters, not too long (a paragraph inside a link is left alone). */
export function scrambleable(text: string): boolean {
  const t = text.trim()
  return t.length >= 2 && t.length <= MAX_CHARS && /[A-Za-z0-9]/.test(t)
}

// ---------------------------------------------------------------- browser part
const TARGETS = 'a, button, [role="button"], summary'
const running = new WeakMap<Element, ScrambleRun>()

function calm(): boolean {
  return document.documentElement.dataset.motion === 'paused' || window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function textSlots(el: Element): Text[] {
  const out: Text[] = []
  const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement?.closest('[aria-hidden="true"], .sr-only, svg') ? NodeFilter.FILTER_REJECT
      : (n.nodeValue ?? '').trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
  })
  for (let n = walk.nextNode(); n; n = walk.nextNode()) out.push(n as Text)
  return out
}

function start(el: Element) {
  if (running.has(el) || calm()) return
  if (el.closest('[data-no-scramble], .monaco-editor')) return
  const nodes = textSlots(el)
  const all = nodes.map((n) => n.nodeValue ?? '').join('')
  if (!nodes.length || !scrambleable(all)) return
  const html = el as HTMLElement
  // screen readers keep hearing the real label while the letters flicker
  const addedLabel = !html.hasAttribute('aria-label') && !html.hasAttribute('aria-labelledby')
  if (addedLabel) html.setAttribute('aria-label', all.trim())
  // keep the width while glyphs of other widths pass through, so neighbours do not jiggle
  const prevMin = html.style.minWidth
  const w = html.getBoundingClientRect().width
  if (w > 0 && getComputedStyle(html).display !== 'inline') html.style.minWidth = `${w}px`
  const run = new ScrambleRun(nodes.map((n) => ({ get: () => n.nodeValue ?? '', set: (v: string) => { n.nodeValue = v } })), performance.now())
  running.set(el, run)
  const tick = () => {
    if (calm()) run.finish()
    if (run.stopped || run.step(performance.now())) {
      running.delete(el)
      if (addedLabel) html.removeAttribute('aria-label')
      html.style.minWidth = prevMin
      return
    }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

let installed = false
/** Installs the site-wide hover/focus scramble once. Safe to call more than once. */
export function installHoverScramble(): void {
  if (installed || typeof document === 'undefined') return
  installed = true
  const onEnter = (e: Event) => {
    const target = (e.target as Element | null)?.closest?.(TARGETS)
    if (!target) return
    // pointerover bubbles from children: only start when the pointer comes from outside the element
    const from = (e as PointerEvent).relatedTarget as Node | null
    if (e.type === 'pointerover' && from && target.contains(from)) return
    start(target)
  }
  document.addEventListener('pointerover', onEnter, true)
  document.addEventListener('focusin', onEnter, true)
}
