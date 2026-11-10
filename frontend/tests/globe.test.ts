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
