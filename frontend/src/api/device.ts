import { getJson, postJson } from './client'

export interface LogEntry {
  n: number
  at: string
  sim_hour: number
  sim_day: string
  tool: string
  args: Record<string, unknown>
  guarded: boolean
  decision: 'ALLOW' | 'DENY' | 'UNGUARDED'
  reason: string
  executed: boolean
  message: string
  facts: string[]
  trace: string[]
}

export interface DeviceSnapshot {
  state: { doors: Record<string, string>; thermostats: Record<string, number>; valves: Record<string, number> }
  clock: { hour: number; day: string }
  log: LogEntry[]
  policy_id: string | null
}

export const deviceState = () => getJson<DeviceSnapshot>('/device/state')
export const setClock = (hour: number, day: string) => postJson<DeviceSnapshot>('/device/clock', { hour, day })
export const resetDevice = () => postJson<DeviceSnapshot>('/device/reset', {})
export const runDemo = (guard: boolean) => postJson<DeviceSnapshot>('/device/demo', { guard })
export const sendCommand = (tool: string, args: Record<string, unknown>, guard: boolean) =>
  postJson<LogEntry>('/device/command', { tool, args, guard })
