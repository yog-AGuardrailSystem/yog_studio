/** Pure geometry for the hero globe (no DOM, no three.js): unit-tested in tests/globe.test.ts. */

/** Small seeded PRNG so a given seed always gives the same dots (stable look, testable). */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** n points spread evenly over the unit sphere (Fibonacci / golden-angle spiral). Flat [x,y,z,...]. */
export function fibonacciSphere(n: number): Float32Array {
  const out = new Float32Array(n * 3)
  const golden = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < n; i++) {
    const y = 1 - (2 * (i + 0.5)) / n
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const th = golden * i
    out[i * 3] = Math.cos(th) * r
    out[i * 3 + 1] = y
    out[i * 3 + 2] = Math.sin(th) * r
  }
  return out
}

/**
 * Break the visible spiral rows of an even sphere with a little noise: each point moves by up to `amount` in a random
 * direction (and so lands slightly inside or outside the surface), which reads as a natural point cloud. Returns a new array.
 */
export function jitterPoints(points: Float32Array, amount: number, seed = 3): Float32Array {
  const rnd = mulberry32(seed)
  const out = new Float32Array(points.length)
  for (let i = 0; i < points.length; i++) out[i] = points[i] + (rnd() * 2 - 1) * amount
  return out
}

/** n random points inside a ball of the given radius (where the dots start before they gather). Flat [x,y,z,...]. */
export function scatterCloud(n: number, radius: number, seed = 7): Float32Array {
  const rnd = mulberry32(seed)
  const out = new Float32Array(n * 3)
  for (let i = 0; i < n; i++) {
    const u = rnd() * 2 - 1
    const th = rnd() * Math.PI * 2
    const r = radius * Math.cbrt(rnd())
    const s = Math.sqrt(1 - u * u)
    out[i * 3] = Math.cos(th) * s * r
    out[i * 3 + 1] = u * r
    out[i * 3 + 2] = Math.sin(th) * s * r
  }
  return out
}

export interface Mask {
  w: number
  h: number
  /** alpha channel, row-major, 0..255 */
  alpha: ArrayLike<number>
}

/**
 * Choose exactly n target positions inside the opaque part of a mask (e.g. a rasterised word).
 * The mask is centred and scaled so its WIDTH spans `worldWidth` world units (y is flipped: canvas y grows down).
 * If the mask has fewer opaque pixels than n, pixels are reused with a sub-pixel jitter. Flat [x,y,z,...], z = 0.
 */
export function pickTargets(mask: Mask, n: number, worldWidth: number, seed = 11): Float32Array {
  const opaque: number[] = []
  let minX = mask.w, maxX = 0, minY = mask.h, maxY = 0
  for (let y = 0; y < mask.h; y++) {
    for (let x = 0; x < mask.w; x++) {
      if (mask.alpha[y * mask.w + x] > 127) {
        opaque.push(y * mask.w + x)
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
      }
    }
  }
  const out = new Float32Array(n * 3)
  if (!opaque.length) return out
  const rnd = mulberry32(seed)
  // Fisher-Yates over the opaque pixel list so the chosen n are an unbiased sample
  for (let i = opaque.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1))
    ;[opaque[i], opaque[j]] = [opaque[j], opaque[i]]
  }
  const spanX = Math.max(1, maxX - minX + 1)
  const scale = worldWidth / spanX
  const cx = (minX + maxX + 1) / 2
  const cy = (minY + maxY + 1) / 2
  for (let i = 0; i < n; i++) {
    const px = opaque[i % opaque.length]
    const reuse = i >= opaque.length
    const x = (px % mask.w) + 0.5 + (reuse ? rnd() - 0.5 : 0)
    const y = Math.floor(px / mask.w) + 0.5 + (reuse ? rnd() - 0.5 : 0)
    out[i * 3] = (x - cx) * scale
    out[i * 3 + 1] = -(y - cy) * scale
    out[i * 3 + 2] = 0
  }
  return out
}

/** A stable pseudo-random number in [0, 1) derived from a position, so a point keeps its own size/brightness forever. */
export function hash01(x: number, y: number, z = 0): number {
  const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453
  return s - Math.floor(s)
}

/** Squared radius of the ball the logo core must stay inside (the orb has radius 1; a little margin keeps it off the skin). */
export const CORE_R2 = 0.92

/**
 * The logo core: `n` points inside the opaque letters of a mask, EXTRUDED through the depth of the ball.
 * Each point keeps its (x, y) inside the letters and gets a z spread over the chord of the ball at that (x, y), so the
 * result is a letter-shaped prism that fills the sphere from front to back. Seen from the side it is a flat band;
 * turned to face the viewer it reads as the letters. The whole cloud is then tilted by `tiltDeg` about the x axis.
 * `depth` (0..1) is how much of the chord the prism fills: 1 = the whole depth, less keeps the letters crisper from the front.
 * `width` is how many orb radii the word spans. Flat [x, y, z, ...]; every point satisfies x^2 + y^2 + z^2 <= CORE_R2.
 */
export function logoVolume(mask: Mask, n: number, width: number, tiltDeg = 10, seed = 21, depth = 1): Float32Array {
  const flat = pickTargets(mask, n, width, seed)
  const rnd = mulberry32(seed + 1)
  const t = (tiltDeg * Math.PI) / 180
  const c = Math.cos(t), s = Math.sin(t)
  for (let i = 0; i < n; i++) {
    const x = flat[i * 3], y = flat[i * 3 + 1]
    const chord = Math.sqrt(Math.max(0, CORE_R2 - x * x - y * y))
    const z = (rnd() * 2 - 1) * chord * depth
    flat[i * 3 + 1] = c * y - s * z
    flat[i * 3 + 2] = s * y + c * z
  }
  return flat
}

/** Indices of a random `keep` fraction (0..1) of `n` points: the sparse outer shell, hover cloud and debris draw only these. */
export function subsetIndices(n: number, keep: number, seed = 5): Uint32Array {
  const rnd = mulberry32(seed)
  const out: number[] = []
  for (let i = 0; i < n; i++) if (rnd() < keep) out.push(i)
  return Uint32Array.from(out)
}
