// Run: npm run test:mirror   (node's built-in test runner, no extra deps)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { evaluate } from '../src/lib/yogMirror.ts'

test('unlock at noon is ALLOW', () => {
  assert.equal(evaluate({ tool: 'unlock_door', hour: 12 }).decision, 'ALLOW')
})
test('unlock at 3am is DENY and DENY beats ALLOW', () => {
  const r = evaluate({ tool: 'unlock_door', hour: 3 })
  assert.equal(r.decision, 'DENY')
  assert.match(r.rule, /night/)
})
test('night window edges: 23:00 and 05:00 deny, 06:00 and 22:00 allow', () => {
  assert.equal(evaluate({ tool: 'unlock_door', hour: 23 }).decision, 'DENY')
  assert.equal(evaluate({ tool: 'unlock_door', hour: 5 }).decision, 'DENY')
  assert.equal(evaluate({ tool: 'unlock_door', hour: 6 }).decision, 'ALLOW')
  assert.equal(evaluate({ tool: 'unlock_door', hour: 22 }).decision, 'ALLOW')
})
test('locking is allowed at night', () => {
  assert.equal(evaluate({ tool: 'lock_door', hour: 3 }).decision, 'ALLOW')
})
test('thermostat 16..28 inclusive allowed, outside default DENY', () => {
  for (const t of [16, 21, 28]) assert.equal(evaluate({ tool: 'set_thermostat', hour: 12, temperature: t }).decision, 'ALLOW')
  for (const t of [15, 29, 40]) {
    const r = evaluate({ tool: 'set_thermostat', hour: 12, temperature: t })
    assert.equal(r.decision, 'DENY')
    assert.equal(r.rule, 'default DENY')
  }
})
test('valve over 50 denied, 50 allowed', () => {
  assert.equal(evaluate({ tool: 'open_valve', hour: 12, percent: 50 }).decision, 'ALLOW')
  assert.equal(evaluate({ tool: 'open_valve', hour: 12, percent: 51 }).decision, 'DENY')
})
