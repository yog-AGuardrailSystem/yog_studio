// traceLines: which source lines decided a request, from either engine's trace. Run with `npm run test:mirror`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { traceLines } from '../src/lib/workbench.ts'

const SRC = ['fact role(alice, admin)', 'fact role(bob, user)', 'rule ok(U):', '    role(U, admin)', 'allow can_x(U, R):', '    ok(U)', '    not role(U, banned)', ''].join('\n')
const REASON = 'allow clause at line 5 matched'

test('Python reference trace: matched facts are support lines', () => {
  const py = ['?- ok(alice)', '  try rule ok(U) (line 3)', '  ?- role(alice, admin)', '    matched fact role(alice, admin)', 'not role(alice, banned)', '  ?- role(alice, banned)', '-> True']
  assert.deepEqual(traceLines(SRC, REASON, py), { deciding: 5, support: [1] })
})

test('C engine trace: a ground goal equal to a fact line is support; non-ground goals and absent facts are not', () => {
  const c = ['?- ok(alice)', 'try rule ok/1 (line 3)', '?- role(alice, admin)', 'try fact role/2 (line 1)', '?- role(alice, banned)', 'try fact role/2 (line 1)', '?- role(_, user)', '-> ALLOW (allow clause at line 5 matched)']
  assert.deepEqual(traceLines(SRC, REASON, c), { deciding: 5, support: [1] })
})
