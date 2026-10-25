import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { deviceState, resetDevice, runDemo, sendCommand, setClock, type DeviceSnapshot } from '../api/device'

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const COMMANDS: { label: string; tool: string; args: Record<string, unknown> }[] = [
  { label: 'Unlock front door', tool: 'unlock_door', args: { door_id: 'front_door' } },
  { label: 'Unlock back door', tool: 'unlock_door', args: { door_id: 'back_door' } },
  { label: 'Lock front door', tool: 'lock_door', args: { door_id: 'front_door' } },
  { label: 'Thermostat 22 C', tool: 'set_thermostat', args: { zone: 'living_room', temperature: 22 } },
  { label: 'Thermostat 35 C', tool: 'set_thermostat', args: { zone: 'living_room', temperature: 35 } },
  { label: 'Open garden tap 30%', tool: 'open_valve', args: { valve_id: 'garden_tap', percent: 30 } },
  { label: 'Open water main 100%', tool: 'open_valve', args: { valve_id: 'water_main', percent: 100 } },
]

export default function DevicePage() {
  const [snap, setSnap] = useState<DeviceSnapshot | null>(null)
  const [guard, setGuard] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [flash, setFlash] = useState<'ALLOW' | 'DENY' | null>(null)

  const refresh = () => deviceState().then(setSnap).catch((e) => setError(String(e.message ?? e)))
  useEffect(() => {
    void refresh()
  }, [])

  async function attempt<T>(job: () => Promise<T>) {
    setError(null)
    try {
      return await job()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function send(tool: string, args: Record<string, unknown>) {
    const r = await attempt(() => sendCommand(tool, args, guard))
    if (r) setFlash(r.decision === 'DENY' ? 'DENY' : 'ALLOW')
    setTimeout(() => setFlash(null), 1800)
    await refresh()
  }

  if (!snap) return <p className="text-sm text-slate-500">{error ?? 'Loading…'}</p>
  const noPolicy = snap.policy_id === null

  return (
    <div className="space-y-4">
      {noPolicy && guard && (
        <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          No approved policy yet. <Link to="/review" className="underline">Approve one on the Review page</Link>; guarded commands are refused until then.
        </div>
      )}
      {flash && (
        <div className={`rounded p-4 text-center text-2xl font-extrabold text-white ${flash === 'DENY' ? 'bg-red-600' : 'bg-green-600'}`} data-testid="flash">
          {flash === 'DENY' ? 'BLOCKED BY YOG' : 'ALLOWED'}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-4 rounded border border-slate-200 bg-white p-3 text-sm">
        <label>
          Simulated hour
          <input
            type="number"
            min={0}
            max={23}
            value={snap.clock.hour}
            className="ml-2 w-16 rounded border border-slate-300 px-1"
            onChange={(e) => attempt(() => setClock(Number(e.target.value), snap.clock.day)).then((s) => s && setSnap(s))}
          />
        </label>
        <label>
          Day
          <select
            value={snap.clock.day}
            className="ml-2 rounded border border-slate-300"
            onChange={(e) => attempt(() => setClock(snap.clock.hour, e.target.value)).then((s) => s && setSnap(s))}
          >
            {DAYS.map((d) => <option key={d}>{d}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={guard} onChange={(e) => setGuard(e.target.checked)} /> YOG guard {guard ? 'ON' : 'OFF (unsafe)'}
        </label>
        <span className="text-xs text-slate-500">policy: {snap.policy_id ?? 'none'}</span>
        <button
          className="ml-auto rounded bg-indigo-600 px-3 py-1.5 font-semibold text-white"
          onClick={() => attempt(() => runDemo(guard)).then((s) => s && setSnap(s))}
        >
          Run agent demo day
        </button>
        <button className="rounded border border-slate-300 px-3 py-1.5" onClick={() => attempt(resetDevice).then((s) => s && setSnap(s))}>
          Reset
        </button>
      </div>

      {error && <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</div>}

      <div className="grid gap-4 md:grid-cols-3" data-testid="device-state">
        <div className="rounded border border-slate-200 bg-white p-3">
          <h3 className="mb-2 font-semibold">Doors</h3>
          {Object.entries(snap.state.doors).map(([k, v]) => (
            <div key={k} className="flex justify-between text-sm">
              <span>{k}</span>
              <b className={v === 'locked' ? 'text-green-700' : 'text-red-700'}>{v === 'locked' ? 'locked' : 'UNLOCKED'}</b>
            </div>
          ))}
        </div>
        <div className="rounded border border-slate-200 bg-white p-3">
          <h3 className="mb-2 font-semibold">Thermostats</h3>
          {Object.entries(snap.state.thermostats).map(([k, v]) => (
            <div key={k} className="flex justify-between text-sm"><span>{k}</span><b>{v} C</b></div>
          ))}
        </div>
        <div className="rounded border border-slate-200 bg-white p-3">
          <h3 className="mb-2 font-semibold">Valves</h3>
          {Object.entries(snap.state.valves).map(([k, v]) => (
            <div key={k} className="flex justify-between text-sm"><span>{k}</span><b>{v}% open</b></div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {COMMANDS.map((c) => (
          <button key={c.label} onClick={() => send(c.tool, c.args)} className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-indigo-50">
            {c.label}
          </button>
        ))}
      </div>

      <div className="max-h-96 overflow-auto rounded border border-slate-200 bg-white" data-testid="device-log">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-100 uppercase text-slate-500">
            <tr><th className="p-2">#</th><th>Sim time</th><th>Command</th><th>Decision</th><th>Result</th></tr>
          </thead>
          <tbody>
            {[...snap.log].reverse().map((e) => (
              <tr key={e.n} className={`border-t border-slate-100 align-top ${e.decision === 'DENY' ? 'bg-red-50' : e.decision === 'ALLOW' ? 'bg-green-50' : 'bg-amber-50'}`}>
                <td className="p-2">{e.n}</td>
                <td>{e.sim_day} {String(e.sim_hour).padStart(2, '0')}:00</td>
                <td className="font-mono">{e.tool}({Object.values(e.args).join(', ')})</td>
                <td className="font-bold">{e.decision}</td>
                <td>{e.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
