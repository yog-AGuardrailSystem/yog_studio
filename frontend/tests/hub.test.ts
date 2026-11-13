// The Studio hub model (boxes, cards, states): pure code, run with `npm run test:mirror`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ACCENTS, REST, accentFor, boxLabel, boxPlaces, cardIndex, cardSlots, hashFor, hubReducer, parseHash, toolsIn } from '../src/lib/hubModel.ts'
import { GROUPS, TOOLS } from '../src/lib/tools.ts'

test('five boxes, named as the stages, and together they hold every tool exactly once', () => {
  assert.deepEqual(GROUPS.map((g) => g.title), ['Build a policy', 'Understand it', 'Test it', 'Ship it', 'Operate it'])
  const all = GROUPS.flatMap((g) => toolsIn(g.id).map((t) => t.id))
  assert.equal(all.length, TOOLS.length)
  assert.equal(new Set(all).size, TOOLS.length)
})

test('every tool has an accent, and no two cards in one box share it', () => {
  for (const t of TOOLS) assert.ok((ACCENTS as readonly string[]).includes(accentFor(t.id)), t.id)
  for (const g of GROUPS) {
    const a = toolsIn(g.id).map((t) => accentFor(t.id))
    assert.equal(new Set(a).size, a.length, `${g.id}: repeated accent`)
  }
  for (const c of ACCENTS) assert.match(c, /^#[0-9a-f]{6}$/)
})

test('card slots: one per card, inside the tray, in order, none on top of another', () => {
  for (const n of [1, 2, 3, 4, 6]) {
    const s = cardSlots(n)
    assert.equal(s.length, n)
    for (const p of s) assert.ok(Math.abs(p.x) <= 1.4)
    for (let i = 1; i < n; i++) assert.ok(s[i].x > s[i - 1].x && s[i].z <= s[i - 1].z)
  }
  assert.deepEqual(cardSlots(0), [])
})

test('box places: five distinct spots, centred; two columns on a phone', () => {
  const wide = boxPlaces(5)
  assert.equal(wide.length, 5)
  assert.equal(new Set(wide.map((p) => `${p.x}|${p.z}`)).size, 5)
  assert.ok(Math.abs(wide.reduce((s, p) => s + p.x, 0)) < 1e-9)
  const phone = boxPlaces(5, 2)
  assert.equal(new Set(phone.map((p) => `${p.x}|${p.z}`)).size, 5)
  assert.ok(Math.max(...phone.map((p) => Math.abs(p.x))) < 3)
})

test('states: open a box, enter one of its cards, go back from anywhere', () => {
  let s = hubReducer(REST, { type: 'open', group: 'test' })
  assert.deepEqual(s, { mode: 'box', group: 'test' })
  assert.deepEqual(hubReducer(REST, { type: 'enter', tool: 'redteam' }), REST)             // cannot enter from rest
  assert.deepEqual(hubReducer(s, { type: 'enter', tool: 'why' }), s)                       // a tool from another box is ignored
  s = hubReducer(s, { type: 'enter', tool: 'redteam' })
  assert.deepEqual(s, { mode: 'enter', group: 'test', tool: 'redteam' })
  assert.deepEqual(hubReducer(s, { type: 'back' }), REST)
  assert.deepEqual(hubReducer(REST, { type: 'back' }), REST)
  assert.deepEqual(hubReducer(REST, { type: 'open', group: 'nope' as never }), REST)
})

test('deep link: #box=<group> opens it; the old #p= share links and junk stay at rest', () => {
  assert.deepEqual(parseHash('#box=ship'), { mode: 'box', group: 'ship' })
  for (const h of ['', '#', '#p=abc', '#box=', '#box=nope', '#box=ship&x=1', '#BOX=ship']) assert.deepEqual(parseHash(h), REST, h)
  assert.equal(hashFor({ mode: 'box', group: 'ship' }), '#box=ship')
  assert.equal(hashFor(REST), '')
  for (const g of GROUPS) assert.deepEqual(parseHash(hashFor({ mode: 'box', group: g.id })), { mode: 'box', group: g.id })
})

test('labels: box title with a count, cards numbered from 01', () => {
  assert.deepEqual(boxLabel('test'), { title: 'Test it', count: 4 })
  assert.equal(cardIndex('test', toolsIn('test')[0].id), '01')
  assert.equal(cardIndex('test', toolsIn('test')[3].id), '04')
})

test('scramble: nothing at 0, the exact text at 1, same length and spaces in between', async () => {
  const { scrambleFrame, revealProgress, GLYPHS } = await import('../src/lib/scramble.ts')
  const text = 'DENY always beats ALLOW.'
  assert.equal(scrambleFrame(text, 1), text)
  assert.equal(scrambleFrame(text, 2), text)
  assert.equal(scrambleFrame(text, 0).trim(), '')
  const mid = scrambleFrame(text, 0.5, () => 0)
  assert.equal(mid.length, text.length)
  assert.equal(mid.slice(0, 12), text.slice(0, 12))                 // the revealed half is the real text
  for (let i = 0; i < text.length; i++) if (text[i] === ' ') assert.ok(mid[i] === ' ' || mid[i] === '\u00a0')
  assert.ok(mid.slice(12, 17).split('').every((c) => GLYPHS.includes(c)))   // a few flickering glyphs ahead of it
  assert.equal(revealProgress(0, 100, 500), 0)
  assert.equal(revealProgress(350, 100, 500), 0.5)
  assert.equal(revealProgress(9999, 100, 500), 1)
  assert.equal(revealProgress(5, 0, 0), 1)
})
