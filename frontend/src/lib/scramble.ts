// The "scrambled text builds in" effect of the About panel, as a pure function so it can be tested.
// At progress 0 nothing is shown; the text is revealed left to right while the characters just ahead of the reveal
// flicker through random glyphs; at progress 1 it is exactly the text.

export const GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+=<>/'

/** `rand` returns a number in [0, 1); pass a fixed one in tests. */
export function scrambleFrame(text: string, progress: number, rand: () => number = Math.random, lead = 6): string {
  if (progress >= 1) return text
  if (progress <= 0) return text.replace(/[^\s]/g, ' ')
  const shown = Math.floor(text.length * progress)
  let out = ''
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (i < shown || /\s/.test(ch)) out += ch
    else if (i < shown + lead) out += GLYPHS[Math.floor(rand() * GLYPHS.length)]
    else out += ' '
  }
  return out
}

/** How far along (0..1) a reveal that started `elapsed` ms ago is, after `delay` ms of waiting, lasting `duration` ms. */
export function revealProgress(elapsed: number, delay: number, duration: number): number {
  if (duration <= 0) return 1
  return Math.min(1, Math.max(0, (elapsed - delay) / duration))
}
