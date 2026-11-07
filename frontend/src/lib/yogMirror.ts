/**
 * yogMirror: a TINY client-side evaluator used ONLY by the /how-it-works demo.
 *
 * It MIRRORS YOG's decision semantics (it is not the engine):
 *   - any matching DENY rule wins            (DENY > ALLOW)
 *   - else any matching ALLOW rule permits   (ALLOW)
 *   - else the action is refused             (default DENY)
 * The rules below restate examples/policies/demo_smart_home.yog:
 *   never unlock between 11pm and 6am; thermostat 16-28; valves at most 50%.
 * The real Studio device page calls the real engine through the API.
 */
export type Decision = 'ALLOW' | 'DENY'

export interface Call {
  tool: 'unlock_door' | 'lock_door' | 'set_thermostat' | 'open_valve'
  hour: number // 0-23, the simulated clock
  temperature?: number
  percent?: number
}

export interface Result {
  decision: Decision
  reason: string
  /** which rule produced the answer, for display */
  rule: string
}

interface Rule {
  effect: 'allow' | 'deny'
  tool: Call['tool']
  rule: string
  reason: string
  when: (c: Call) => boolean
}

export const RULES: Rule[] = [
  { effect: 'allow', tool: 'unlock_door', rule: 'allow can_unlock_door', reason: 'the assistant role may unlock doors', when: () => true },
  { effect: 'allow', tool: 'lock_door', rule: 'allow can_lock_door', reason: 'the assistant role may lock doors', when: () => true },
  {
    effect: 'allow',
    tool: 'set_thermostat',
    rule: 'allow can_set_thermostat',
    reason: 'temperature is between 16 and 28',
    when: (c) => c.temperature !== undefined && c.temperature >= 16 && c.temperature <= 28,
  },
  { effect: 'allow', tool: 'open_valve', rule: 'allow can_open_valve', reason: 'the assistant role may open valves', when: () => true },
  {
    effect: 'deny',
    tool: 'unlock_door',
    rule: 'deny can_unlock_door (night)',
    reason: 'doors may not be unlocked between 11pm and 6am',
    when: (c) => c.hour >= 23 || c.hour < 6,
  },
  {
    effect: 'deny',
    tool: 'open_valve',
    rule: 'deny can_open_valve (over 50%)',
    reason: 'valves may open at most 50 percent',
    when: (c) => (c.percent ?? 0) > 50,
  },
]

export function evaluate(call: Call): Result {
  const hits = RULES.filter((r) => r.tool === call.tool && r.when(call))
  const deny = hits.find((r) => r.effect === 'deny')
  if (deny) return { decision: 'DENY', reason: deny.reason, rule: deny.rule }
  const allow = hits.find((r) => r.effect === 'allow')
  if (allow) return { decision: 'ALLOW', reason: allow.reason, rule: allow.rule }
  return { decision: 'DENY', reason: 'no rule allows this action (default DENY)', rule: 'default DENY' }
}
