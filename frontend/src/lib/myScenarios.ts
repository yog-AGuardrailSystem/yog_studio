import type { TestCase } from '../api/tools'

/** Scenarios the user chose to keep (from Red-Team, or typed): a plain list in this browser. They are the
 *  tests that Gap Analyzer and Test Strength judge the policy with. */
const KEY = 'yog.myScenarios'
const MAX = 150

export function loadScenarios(): TestCase[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(raw) ? raw.filter(valid).slice(0, MAX) : []
  } catch {
    return []
  }
}

function valid(x: unknown): x is TestCase {
  const t = x as TestCase
  return !!t && typeof t.actor === 'string' && typeof t.action === 'string' && typeof t.resource === 'string' &&
    Array.isArray(t.context) && (t.expected === 'ALLOW' || t.expected === 'DENY')
}

export const sameScenario = (a: TestCase, b: TestCase) =>
  a.actor === b.actor && a.action === b.action && a.resource === b.resource && a.expected === b.expected && a.context.join('|') === b.context.join('|')

export function saveScenarios(list: TestCase[]): void {
  try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX))) } catch { /* storage unavailable: the list just is not kept */ }
}

/** Adds one (ignoring exact duplicates). Returns the new list. */
export function addScenario(t: TestCase): TestCase[] {
  const cur = loadScenarios()
  if (cur.some((x) => sameScenario(x, t))) return cur
  const next = [...cur, t].slice(0, MAX)
  saveScenarios(next)
  return next
}

export const describeScenario = (t: TestCase) => `${t.action}(${t.actor}, ${t.resource})${t.context.length ? ' with ' + t.context.join(', ') : ''} → ${t.expected}`
