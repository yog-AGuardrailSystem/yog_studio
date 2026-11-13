// The Studio hub as plain data: which tools sit in which box, where things stand in the scene, and the few states the hub
// can be in. No React and no three.js here, so it is unit-tested with `npm run test:mirror`.
import { GROUPS, TOOLS, type StudioTool, type ToolGroup } from './tools.ts'

/** One accent per card, as in the reference: a card turns this colour when you hover it. Hand-picked, all readable on black. */
export const ACCENTS = ['#a855f7', '#3b82f6', '#22d3ee', '#ef4444', '#ec4899', '#f97316'] as const

export const GOLD = '#f5b942'

export function toolsIn(group: ToolGroup): StudioTool[] {
  return TOOLS.filter((t) => t.group === group)
}

/** The accent of a tool: stable, and neighbours in the same box never share one. */
export function accentFor(toolId: string): string {
  const i = TOOLS.findIndex((t) => t.id === toolId)
  return ACCENTS[(i < 0 ? 0 : i) % ACCENTS.length]
}

export interface Slot { x: number; z: number; lean: number }

/** Where card `i` of `n` stands inside an opened box (box-local units; the tray is about 3.2 wide). Cards are spread along x and
 *  step back a little, each leaning against the next like the reference. */
export function cardSlots(n: number): Slot[] {
  if (n < 1) return []
  const span = Math.min(2.6, 0.62 * n)
  return Array.from({ length: n }, (_, i) => {
    const t = n === 1 ? 0.5 : i / (n - 1)
    return { x: -span / 2 + t * span, z: -0.18 * i, lean: 0.34 }
  })
}

export interface BoxPlace { x: number; z: number; yaw: number }

/** Five boxes on a shallow arc facing the camera. With fewer `columns` than boxes (a phone) they stack in rows instead. */
export function boxPlaces(count = GROUPS.length, columns = count): BoxPlace[] {
  if (columns >= count) {
    const gap = 4.1
    return Array.from({ length: count }, (_, i) => {
      const k = i - (count - 1) / 2
      return { x: k * gap, z: -Math.abs(k) * 0.55, yaw: -k * 0.07 }
    })
  }
  const rows = Math.ceil(count / columns)
  return Array.from({ length: count }, (_, i) => {
    const r = Math.floor(i / columns), c = i % columns
    const inRow = Math.min(columns, count - r * columns)
    return { x: (c - (inRow - 1) / 2) * 4.1, z: -(r - (rows - 1) / 2) * 4.2, yaw: 0 }
  })
}

// ---- the states of the hub ----
export type HubState =
  | { mode: 'rest' }
  | { mode: 'box'; group: ToolGroup }
  | { mode: 'enter'; group: ToolGroup; tool: string }

export type HubAction =
  | { type: 'open'; group: ToolGroup }
  | { type: 'enter'; tool: string }
  | { type: 'back' }

export const REST: HubState = { mode: 'rest' }

export function isGroup(v: unknown): v is ToolGroup {
  return typeof v === 'string' && GROUPS.some((g) => g.id === v)
}

export function hubReducer(s: HubState, a: HubAction): HubState {
  switch (a.type) {
    case 'open':
      return isGroup(a.group) ? { mode: 'box', group: a.group } : s
    case 'enter': {
      if (s.mode !== 'box') return s
      return toolsIn(s.group).some((t) => t.id === a.tool) ? { mode: 'enter', group: s.group, tool: a.tool } : s
    }
    case 'back':
      return s.mode === 'rest' ? s : REST
  }
}

/** `#box=test` opens that box; anything else (including the old `#p=` share links) is the resting view. */
export function parseHash(hash: string): HubState {
  const m = /^#box=([a-z]+)$/.exec(hash)
  return m && isGroup(m[1]) ? { mode: 'box', group: m[1] } : REST
}

export function hashFor(s: HubState): string {
  return s.mode === 'rest' ? '' : `#box=${s.group}`
}

export function boxLabel(group: ToolGroup): { title: string; count: number } {
  const g = GROUPS.find((x) => x.id === group)!
  return { title: g.title, count: toolsIn(group).length }
}

/** Two-digit number shown in the hover label ("02"). */
export function cardIndex(group: ToolGroup, toolId: string): string {
  const i = toolsIn(group).findIndex((t) => t.id === toolId)
  return String(i + 1).padStart(2, '0')
}
