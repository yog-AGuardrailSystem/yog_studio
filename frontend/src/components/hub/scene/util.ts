import * as THREE from 'three'

/** Longest step one frame may advance the animations: real time on slow machines, but no jump after a hidden tab. */
export const MAX_DT = 0.25

/** Frame-rate independent approach of `a` toward `b`. */
export const damp = (a: number, b: number, lambda: number, dt: number) => a + (b - a) * (1 - Math.exp(-lambda * dt))

export const ease = {
  outCubic: (t: number) => 1 - Math.pow(1 - t, 3),
  inOutCubic: (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  /** Ends a little past 1 and settles back: the lid's hinge overshoot. */
  outBack: (t: number) => { const c1 = 1.4, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2) },
}

const _v = new THREE.Vector3()
/** Moves a real DOM button onto the screen rectangle of a 3D object's local box (`min`..`max`). Hidden when `show` is false. */
export function placeHit(el: HTMLElement | undefined, obj: THREE.Object3D, min: THREE.Vector3, max: THREE.Vector3,
  camera: THREE.Camera, w: number, h: number, show: boolean) {
  if (!el) return
  if (!show) { if (el.style.display !== 'none') el.style.display = 'none'; return }
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (let i = 0; i < 8; i++) {
    _v.set(i & 1 ? max.x : min.x, i & 2 ? max.y : min.y, i & 4 ? max.z : min.z).applyMatrix4(obj.matrixWorld).project(camera)
    const sx = (_v.x * 0.5 + 0.5) * w, sy = (-_v.y * 0.5 + 0.5) * h
    x0 = Math.min(x0, sx); x1 = Math.max(x1, sx); y0 = Math.min(y0, sy); y1 = Math.max(y1, sy)
  }
  const s = el.style
  if (s.display === 'none') s.display = ''
  const t = `translate3d(${Math.round(x0)}px, ${Math.round(y0)}px, 0)`      // whole pixels: a tiny camera drift must not make it "move"
  if (s.transform !== t) s.transform = t
  const ww = `${Math.max(0, Math.round(x1 - x0))}px`, hh = `${Math.max(0, Math.round(y1 - y0))}px`
  if (s.width !== ww) s.width = ww
  if (s.height !== hh) s.height = hh
}
