// The tool registry and the saved-scenarios helper: pure code, run with `npm run test:mirror`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { GROUPS, TOOLS } from '../src/lib/tools.ts'
import { addScenario, describeScenario, loadScenarios, sameScenario, saveScenarios } from '../src/lib/myScenarios.ts'

test('every tool has a unique id, a unique route and a known group', () => {
  assert.equal(new Set(TOOLS.map((t) => t.id)).size, TOOLS.length)
  assert.equal(new Set(TOOLS.map((t) => t.to)).size, TOOLS.length)
  const groups = new Set(GROUPS.map((g) => g.id))
  for (const t of TOOLS) assert.ok(groups.has(t.group), `${t.id}: unknown group ${t.group}`)
  for (const g of GROUPS) assert.ok(TOOLS.some((t) => t.group === g.id), `group ${g.id} is empty`)
})

test('every tool explains itself: purpose, three steps, and what it does not do', () => {
  for (const t of TOOLS) {
    assert.ok(t.name.length > 1 && t.purpose.endsWith('.'), t.id)
    assert.equal(t.how.length, 3, t.id)
    for (const s of t.how) assert.ok(s.length > 10, `${t.id}: step too short`)
    assert.ok(t.limit.length > 15, `${t.id}: missing limit`)
  }
})

test('routes are absolute paths and every Studio tool page lives under /studio', () => {
  for (const t of TOOLS) assert.ok(t.to.startsWith('/'), t.id)
  const own = ['why', 'map', 'gaps', 'redteam', 'strength', 'templates', 'history', 'audit', 'replay', 'sdk', 'export', 'scorecard']
  for (const id of own) assert.ok(TOOLS.find((t) => t.id === id)?.to.startsWith('/studio/'), id)
})

test('nothing is marked ready without a route (planned tools are honest)', () => {
  for (const t of TOOLS) if (t.status === 'ready') assert.ok(t.to.length > 1, t.id)
})

test('the tool names are unique, so the hub and the how-it-works page never show two of the same', () => {
  assert.equal(new Set(TOOLS.map((t) => t.name)).size, TOOLS.length)
})

// ---- saved scenarios (a tiny in-memory localStorage)
function stubStorage() {
  const m = new Map<string, string>()
  ;(globalThis as unknown as { localStorage: unknown }).localStorage = {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
  }
  return m
}
const sc = (over = {}) => ({ actor: 'agent', action: 'can_unlock_door', resource: 'front_door', context: ['hour(now, 3)'], expected: 'DENY' as const, ...over })

test('saved scenarios: add, de-duplicate, keep order, describe', () => {
  stubStorage()
  assert.deepEqual(loadScenarios(), [])
  addScenario(sc())
  addScenario(sc())
  assert.equal(addScenario(sc({ context: ['hour(now, 4)'] })).length, 2)
  assert.equal(loadScenarios()[1].context[0], 'hour(now, 4)')
  assert.equal(describeScenario(sc()), 'can_unlock_door(agent, front_door) with hour(now, 3) → DENY')
  assert.equal(describeScenario(sc({ context: [] })), 'can_unlock_door(agent, front_door) → DENY')
})

test('saved scenarios: equality looks at every field', () => {
  assert.ok(sameScenario(sc(), sc()))
  assert.ok(!sameScenario(sc(), sc({ expected: 'ALLOW' })))
  assert.ok(!sameScenario(sc(), sc({ resource: 'back_door' })))
  assert.ok(!sameScenario(sc(), sc({ context: [] })))
})

test('saved scenarios: junk in storage is ignored, not thrown', () => {
  const m = stubStorage()
  m.set('yog.myScenarios', '{not json')
  assert.deepEqual(loadScenarios(), [])
  m.set('yog.myScenarios', JSON.stringify([sc(), { actor: 1 }, null, 'x', sc({ expected: 'MAYBE' })]))
  assert.equal(loadScenarios().length, 1)
  m.set('yog.myScenarios', '"a string"')
  assert.deepEqual(loadScenarios(), [])
})

test('saved scenarios: capped at 150 and survives missing storage', () => {
  stubStorage()
  saveScenarios(Array.from({ length: 200 }, (_, i) => sc({ resource: `r${i}` })))
  assert.equal(loadScenarios().length, 150)
  ;(globalThis as unknown as { localStorage: unknown }).localStorage = undefined
  assert.deepEqual(loadScenarios(), [])
  assert.doesNotThrow(() => saveScenarios([sc()]))
  assert.equal(addScenario(sc()).length, 1)
})
