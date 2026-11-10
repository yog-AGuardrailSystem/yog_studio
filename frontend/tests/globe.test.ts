// Run: npm run test:mirror   (node's built-in test runner)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fibonacciSphere, jitterPoints, mulberry32, pickTargets, scatterCloud, type Mask } from '../src/lib/globePoints.ts'

test('every sphere point lies on the unit sphere', () => {
  const p = fibonacciSphere(500)
  assert.equal(p.length, 1500)
  for (let i = 0; i < 500; i++) {
    assert.ok(Math.abs(Math.hypot(p[i * 3], p[i * 3 + 1], p[i * 3 + 2]) - 1) < 1e-5)
  }
})

test('sphere points are evenly spread: each octant holds about an eighth', () => {
  const n = 4000
  const p = fibonacciSphere(n)
  const bins = new Array(8).fill(0)
  for (let i = 0; i < n; i++) bins[(p[i * 3] > 0 ? 1 : 0) + (p[i * 3 + 1] > 0 ? 2 : 0) + (p[i * 3 + 2] > 0 ? 4 : 0)]++
  for (const b of bins) assert.ok(Math.abs(b - n / 8) < n * 0.03, `octant has ${b}`)
})

test('jitter nudges points by at most the amount, keeps the length, and is deterministic', () => {
  const p = fibonacciSphere(200)
  const j = jitterPoints(p, 0.03, 9)
  assert.equal(j.length, p.length)
  let moved = 0
  for (let i = 0; i < p.length; i++) {
    assert.ok(Math.abs(j[i] - p[i]) <= 0.03 + 1e-6)
    if (j[i] !== p[i]) moved++
  }
  assert.ok(moved > p.length * 0.9)
  assert.deepEqual(j, jitterPoints(p, 0.03, 9))
  assert.deepEqual(p, fibonacciSphere(200), 'the input is not modified')
})

test('the same seed gives the same numbers, a different seed does not', () => {
  const a = mulberry32(5), b = mulberry32(5), c = mulberry32(6)
  const x = [a(), a(), a()], y = [b(), b(), b()], z = [c(), c(), c()]
  assert.deepEqual(x, y)
  assert.notDeepEqual(x, z)
  assert.ok(x.every((v) => v >= 0 && v < 1))
})

test('the scatter cloud stays inside its radius and is deterministic', () => {
  const a = scatterCloud(300, 3, 1), b = scatterCloud(300, 3, 1)
  assert.deepEqual(a, b)
  for (let i = 0; i < 300; i++) assert.ok(Math.hypot(a[i * 3], a[i * 3 + 1], a[i * 3 + 2]) <= 3 + 1e-5)
})

/** a 40x10 mask: only the left 10 columns are opaque (a stand-in for a letter) */
function mask(): Mask {
  const w = 40, h = 10
  const alpha = new Uint8Array(w * h)
  for (let y = 0; y < h; y++) for (let x = 0; x < 10; x++) alpha[y * w + x] = 255
  return { w, h, alpha }
}

test('pickTargets returns exactly n points, all inside the opaque area, centred', () => {
  const m = mask()
  const t = pickTargets(m, 60, 2)
  assert.equal(t.length, 180)
  const scale = 2 / 10                       // the opaque span is 10 px wide -> 2 world units
  for (let i = 0; i < 60; i++) {
    assert.ok(Math.abs(t[i * 3]) <= 1 + 1e-6, 'x within the word width')
    assert.ok(Math.abs(t[i * 3 + 1]) <= 5 * scale + 1e-6, 'y within the word height')
    assert.equal(t[i * 3 + 2], 0)
  }
  const mean = (k: number) => Array.from({ length: 60 }, (_, i) => t[i * 3 + k]).reduce((a, b) => a + b, 0) / 60
  assert.ok(Math.abs(mean(0)) < 0.35 && Math.abs(mean(1)) < 0.35, 'centred on the word')
})

test('pickTargets reuses pixels with jitter when asked for more points than pixels', () => {
  const m = mask()                                   // 100 opaque pixels
  const t = pickTargets(m, 400, 2)
  assert.equal(t.length, 1200)
  const distinct = new Set(Array.from({ length: 400 }, (_, i) => `${t[i * 3].toFixed(4)},${t[i * 3 + 1].toFixed(4)}`))
  assert.ok(distinct.size > 300, 'jitter keeps the repeated dots from stacking exactly')
})

test('pickTargets is deterministic for a seed, different for another', () => {
  const m = mask()
  assert.deepEqual(pickTargets(m, 50, 2, 3), pickTargets(m, 50, 2, 3))
  assert.notDeepEqual(pickTargets(m, 50, 2, 3), pickTargets(m, 50, 2, 4))
})

test('an empty mask gives zeros instead of crashing', () => {
  const t = pickTargets({ w: 4, h: 4, alpha: new Uint8Array(16) }, 5, 2)
  assert.equal(t.length, 15)
  assert.ok(t.every((v) => v === 0))
})

import { CORE_R2, hash01, logoVolume, subsetIndices } from '../src/lib/globePoints.ts'

/** a 60x20 mask with two separate opaque blocks, like two letters */
function letters(): Mask {
  const w = 60, h = 20
  const alpha = new Uint8Array(w * h)
  for (let y = 2; y < 18; y++) { for (let x = 4; x < 20; x++) alpha[y * w + x] = 255; for (let x = 36; x < 52; x++) alpha[y * w + x] = 255 }
  return { w, h, alpha }
}

test('the logo core has exactly n points, all inside the ball', () => {
  const v = logoVolume(letters(), 800, 1.3, 10)
  assert.equal(v.length, 2400)
  for (let i = 0; i < 800; i++) assert.ok(v[i * 3] ** 2 + v[i * 3 + 1] ** 2 + v[i * 3 + 2] ** 2 <= CORE_R2 + 1e-5, `point ${i} is outside the ball`)
})

test('the logo core is a prism: it spreads across the depth of the ball, and its footprint is the letters', () => {
  const v = logoVolume(letters(), 4000, 1.3, 0)           // no tilt: the footprint is exactly the letter shapes
  let zMin = 1, zMax = -1, inGap = 0
  for (let i = 0; i < 4000; i++) {
    zMin = Math.min(zMin, v[i * 3 + 2]); zMax = Math.max(zMax, v[i * 3 + 2])
    if (Math.abs(v[i * 3]) < 0.1) inGap++                 // the gap between the two blocks is at x = 0 (centred)
  }
  assert.ok(zMin < -0.6 && zMax > 0.6, `z only spans ${zMin.toFixed(2)}..${zMax.toFixed(2)}`)
  assert.equal(inGap, 0, 'no points between the letters')
})

test('seen side-on the core is a thin band, seen front-on it is wide: nothing needs to rearrange', () => {
  const v = logoVolume(letters(), 3000, 1.3, 0)
  const span = (k: number) => { let a = 1, b = -1; for (let i = 0; i < 3000; i++) { a = Math.min(a, v[i * 3 + k]); b = Math.max(b, v[i * 3 + k]) } return b - a }
  assert.ok(span(0) > 1.2, 'wide from the front')
  assert.ok(span(1) < 0.8, 'short in height')
  assert.ok(span(2) > 1.2, 'deep through the ball')
})

test('the core is deterministic and different for another seed', () => {
  assert.deepEqual(logoVolume(letters(), 100, 1.3, 10, 4), logoVolume(letters(), 100, 1.3, 10, 4))
  assert.notDeepEqual(logoVolume(letters(), 100, 1.3, 10, 4), logoVolume(letters(), 100, 1.3, 10, 5))
})

test('subsetIndices keeps about the requested fraction, sorted, deterministic', () => {
  const s = subsetIndices(10000, 0.24, 3)
  assert.ok(Math.abs(s.length - 2400) < 150, String(s.length))
  for (let i = 1; i < s.length; i++) assert.ok(s[i] > s[i - 1])
  assert.deepEqual(s, subsetIndices(10000, 0.24, 3))
  assert.equal(subsetIndices(100, 0).length, 0)
  assert.equal(subsetIndices(100, 1).length, 100)
})

test('hash01 is in [0, 1), stable, and varies with its inputs', () => {
  const seen = new Set<number>()
  for (let i = 0; i < 200; i++) { const h = hash01(i * 0.37, i * 0.11, i * 0.07); assert.ok(h >= 0 && h < 1); seen.add(h) }
  assert.ok(seen.size > 190)
  assert.equal(hash01(1.5, -2, 0.25), hash01(1.5, -2, 0.25))
})

test('a shallower prism keeps its depth within the requested share of the chord', () => {
  const v = logoVolume(letters(), 3000, 1.3, 0, 21, 0.5)
  for (let i = 0; i < 3000; i++) {
    const chord = Math.sqrt(CORE_R2 - v[i * 3] ** 2 - v[i * 3 + 1] ** 2)
    assert.ok(Math.abs(v[i * 3 + 2]) <= chord * 0.5 + 1e-5)
  }
})
