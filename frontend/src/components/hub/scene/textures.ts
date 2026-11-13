// Canvas-drawn textures for the hub scene: card faces, engraved cabinet text, glows. Drawn once, cached, never per frame.
import * as THREE from 'three'
import { iconFor } from '../../../lib/hubIcons'

export function canvasTexture(w: number, h: number, draw: (g: CanvasRenderingContext2D) => void, srgb = true): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const g = c.getContext('2d')!
  draw(g)
  const t = new THREE.CanvasTexture(c)
  if (srgb) t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 8
  return t
}

const cache = new Map<string, THREE.Texture>()
function cached(key: string, make: () => THREE.Texture): THREE.Texture {
  let t = cache.get(key)
  if (!t) { t = make(); cache.set(key, t) }
  return t
}

/** A soft white round glow (tinted by the material's colour): floor pools, light leaking from a lid, dust. */
export const radialGlow = () => cached('radial', () => canvasTexture(128, 128, (g) => {
  const r = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.25, 'rgba(255,255,255,0.45)'); r.addColorStop(0.6, 'rgba(255,255,255,0.08)'); r.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = r; g.fillRect(0, 0, 128, 128)
}, false))

/** A long soft streak, bright at the right end and fading left: the beam from the plug and its trace on each card. */
export const streak = () => cached('streak', () => canvasTexture(256, 64, (g) => {
  const lin = g.createLinearGradient(0, 0, 256, 0)
  lin.addColorStop(0, 'rgba(255,255,255,0)'); lin.addColorStop(0.65, 'rgba(255,255,255,0.35)'); lin.addColorStop(1, 'rgba(255,255,255,1)')
  g.fillStyle = lin; g.fillRect(0, 0, 256, 64)
  g.globalCompositeOperation = 'destination-in'
  const v = g.createLinearGradient(0, 0, 0, 64)
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(0.5, 'rgba(0,0,0,1)'); v.addColorStop(1, 'rgba(0,0,0,0)')
  g.fillStyle = v; g.fillRect(0, 0, 256, 64)
}, false))

/** The dark floor overlay: almost opaque at the edges, thinner in the middle, so the mirror shows only near the cabinets. */
export const floorFade = () => cached('floorFade', () => canvasTexture(256, 256, (g) => {
  const r = g.createRadialGradient(128, 128, 10, 128, 128, 128)
  r.addColorStop(0, 'rgba(26,25,22,0.66)'); r.addColorStop(0.35, 'rgba(14,13,12,0.86)'); r.addColorStop(0.7, 'rgba(5,5,4,0.96)'); r.addColorStop(1, 'rgba(0,0,0,1)')   // a lit grey floor round the cabinets, fading to black
  g.fillStyle = r; g.fillRect(0, 0, 256, 256)
}, true))   // sRGB: the greys are meant as seen, not as linear light

/** The smoked-glass inside of the lid: a faint vertical sheen. */
export const lidGlass = () => cached('lidGlass', () => canvasTexture(64, 256, (g) => {
  const v = g.createLinearGradient(0, 0, 0, 256)
  v.addColorStop(0, '#1d1a12'); v.addColorStop(0.45, '#0d0c09'); v.addColorStop(1, '#16130c')
  g.fillStyle = v; g.fillRect(0, 0, 64, 256)
}))

/** The far backdrop: a dim warm glow behind the cabinets fading to black, like the reference's vignette. */
export const backdrop = () => cached('backdrop', () => canvasTexture(256, 256, (g) => {
  const r = g.createRadialGradient(128, 150, 0, 128, 150, 140)
  r.addColorStop(0, '#211e18'); r.addColorStop(0.45, '#0d0c0a'); r.addColorStop(1, '#000000')
  g.fillStyle = r; g.fillRect(0, 0, 256, 256)
}))

function spaced(g: CanvasRenderingContext2D, text: string, x: number, y: number, spacing: number) {
  let cx = x
  for (const ch of text) { g.fillText(ch, cx, y); cx += g.measureText(ch).width + spacing }
  return cx - spacing
}
function spacedWidth(g: CanvasRenderingContext2D, text: string, spacing: number) {
  let w = 0
  for (const ch of text) w += g.measureText(ch).width + spacing
  return w - spacing
}

/** "YOG STUDIO  /  03 TEST IT" in small, very widely spaced capitals, as engraved on the reference's front face. */
export function engraving(left: string, right: string): THREE.CanvasTexture {
  return canvasTexture(2048, 96, (g) => {
    g.clearRect(0, 0, 2048, 96)
    g.fillStyle = '#fff'
    g.textBaseline = 'middle'
    g.font = '500 30px "JetBrains Mono", ui-monospace, monospace'
    const sp = 22
    const a = spacedWidth(g, left, sp), b = spacedWidth(g, right, sp), slash = 80
    let x = (2048 - (a + slash * 2 + 18 + b)) / 2
    x = spaced(g, left, x, 48, sp) + slash
    g.fillText('/', x, 48)
    spaced(g, right, x + 18 + slash, 48, sp)
  })
}

/** The face of a glass card: index and title along the top, line icon lower-left, a small mark top-right. White on clear,
 *  so the material colour tints it (gold at rest, white when lit). Aspect 1.6 : 1. */
export function cardFace(index: string, title: string, toolId: string): THREE.CanvasTexture {
  const W = 640, H = 400
  return canvasTexture(W, H, (g) => {
    g.clearRect(0, 0, W, H)
    g.fillStyle = '#fff'; g.strokeStyle = '#fff'
    g.textBaseline = 'middle'
    g.globalAlpha = 0.85
    g.font = '500 24px "JetBrains Mono", ui-monospace, monospace'
    g.fillText(index, 34, 44)
    g.globalAlpha = 0.9
    g.font = '600 34px "Inter Tight", Inter, system-ui, sans-serif'
    g.fillText(title, 86, 44)
    // corner mark
    g.globalAlpha = 0.6
    g.lineWidth = 3
    g.beginPath(); g.moveTo(W - 46, 52); g.lineTo(W - 30, 36); g.moveTo(W - 42, 36); g.lineTo(W - 30, 36); g.lineTo(W - 30, 48); g.stroke()
    // icon, lower-left, in a 24-unit grid scaled up
    g.globalAlpha = 1
    g.save()
    g.translate(40, H - 150)
    g.scale(4.4, 4.4)
    g.lineWidth = 1.5; g.lineCap = 'round'; g.lineJoin = 'round'
    try { g.stroke(new Path2D(iconFor(toolId))) } catch { /* a broken path is skipped, never fatal */ }
    g.restore()
  })
}
