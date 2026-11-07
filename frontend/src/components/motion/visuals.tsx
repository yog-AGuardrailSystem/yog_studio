import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useState } from 'react'
import { evaluate, type Call } from '../../lib/yogMirror'
import { DenyStamp } from './DenyStamp'
import { TypeText } from './TypeText'

/** Every visual takes `active`: it plays when true, and rests in its finished state under reduced motion. */
type V = { active: boolean }

function useOn(active: boolean) {
  const reduce = useReducedMotion()
  return { on: active || !!reduce, reduce: !!reduce }
}

const Card = ({ children, label }: { children: React.ReactNode; label: string }) => (
  <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-900/5" role="img" aria-label={label}>
    {children}
  </div>
)

/* 1 ─ Upload + detect */
const CODE = [
  'mcp = FastMCP("smart-home")',
  '',
  '@mcp.tool()',
  'def unlock_door(door_id: str, pin=None):',
  '    """Unlock a door."""',
  '    DOORS[door_id] = "unlocked"',
]
export function UploadVisual({ active }: V) {
  const { on } = useOn(active)
  return (
    <Card label="Detector finds an MCP server in the uploaded file">
      <p className="font-mono text-xs text-slate-500">smart_home_mcp.py</p>
      <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-200">
        {CODE.map((l, i) => (
          <motion.div
            key={i}
            animate={{ backgroundColor: on && (i === 0 || i === 2) ? 'rgba(250,204,21,0.25)' : 'rgba(250,204,21,0)' }}
            transition={{ delay: on ? 0.5 + i * 0.05 : 0, duration: 0.4 }}
          >
            {l || ' '}
          </motion.div>
        ))}
      </pre>
      <motion.div
        className="mt-4 inline-flex items-center gap-2 rounded-full bg-emerald-100 px-3 py-1 text-sm font-semibold text-emerald-800"
        initial={false}
        animate={on ? { scale: 1, opacity: 1 } : { scale: 0.6, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 400, damping: 18, delay: on ? 0.9 : 0 }}
      >
        MCP server · 0.95
      </motion.div>
      <p className="mt-2 text-xs text-slate-500">Evidence: the highlighted lines. The file is read, never run.</p>
    </Card>
  )
}

/* 2 ─ Tools */
const TOOLS: [string, string][] = [
  ['unlock_door', 'door_id, pin'],
  ['lock_door', 'door_id'],
  ['set_thermostat', 'zone, temperature'],
  ['open_valve', 'valve_id, percent'],
  ['get_status', 'device_id'],
]
export function ToolsVisual({ active }: V) {
  const { on } = useOn(active)
  return (
    <Card label="Tools found in the agent">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">5 tools found</p>
      <ul className="mt-3 space-y-2">
        {TOOLS.map(([n, p], i) => (
          <motion.li
            key={n}
            className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2"
            initial={false}
            animate={on ? { opacity: 1, x: 0 } : { opacity: 0, x: -24 }}
            transition={{ delay: on ? i * 0.12 : 0, duration: 0.35 }}
          >
            <span className="font-mono text-sm font-semibold">{n}</span>
            <span className="font-mono text-xs text-slate-500">{p}</span>
          </motion.li>
        ))}
      </ul>
    </Card>
  )
}

/* 3 ─ Translate */
const RULE = 'The agent may never unlock the door between 11pm and 6am.'
const YOG = ['deny can_unlock_door(Actor, Door):', '    hour(now, H)', '    H >= 23', 'deny can_unlock_door(Actor, Door):', '    hour(now, H)', '    H < 6']
export function TranslateVisual({ active }: V) {
  const { on, reduce } = useOn(active)
  const [typed, setTyped] = useState(false)
  const showRest = reduce || typed
  return (
    <Card label="An English rule becomes YOG">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Your rule</p>
      <p className="mt-1 min-h-[3rem] rounded-lg bg-slate-50 p-3 text-sm">
        <TypeText text={RULE} run={active} onStart={() => setTyped(false)} onDone={() => setTyped(true)} />
      </p>
      <motion.div className="mt-3" initial={false} animate={showRest ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Similar examples retrieved</p>
        <div className="mt-1 flex flex-wrap gap-2">
          {['never-at-night', 'time-window', 'door-lock'].map((e, i) => (
            <motion.span
              key={e}
              className="rounded-full border border-slate-200 px-2 py-0.5 font-mono text-xs"
              initial={false}
              animate={showRest ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.8 }}
              transition={{ delay: showRest ? i * 0.15 : 0 }}
            >
              {e}
            </motion.span>
          ))}
        </div>
      </motion.div>
      <pre className="mt-3 rounded-lg bg-slate-950 p-3 font-mono text-xs leading-6 text-slate-100">
        {YOG.map((l, i) => (
          <motion.div
            key={i}
            initial={false}
            animate={showRest ? { opacity: 1 } : { opacity: 0 }}
            transition={{ delay: showRest ? 0.5 + i * 0.12 : 0 }}
          >
            {l}
          </motion.div>
        ))}
      </pre>
      {!on && <span className="sr-only">Animation starts when this step is in view.</span>}
    </Card>
  )
}

/* 4 ─ Verify + approve */
export function VerifyVisual({ active }: V) {
  const { on } = useOn(active)
  const steps: [string, string, boolean][] = [
    ['Attempt 1', 'error: unknown predicate “can_unlock”', false],
    ['Attempt 2', 'syntax and semantic checks pass', true],
  ]
  return (
    <Card label="Engine verifies the draft, then you approve">
      <div className="space-y-2">
        {steps.map(([t, d, ok], i) => (
          <motion.div
            key={t}
            className={`rounded-lg border px-3 py-2 text-sm ${ok ? 'border-emerald-300 bg-emerald-50' : 'border-red-200 bg-red-50'}`}
            initial={false}
            animate={on ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
            transition={{ delay: on ? 0.2 + i * 0.7 : 0 }}
          >
            <span className="font-semibold">{ok ? '✓' : '✕'} {t}</span> <span className="text-slate-600">{d}</span>
          </motion.div>
        ))}
      </div>
      <motion.p
        className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-700"
        initial={false}
        animate={on ? { opacity: 1 } : { opacity: 0 }}
        transition={{ delay: on ? 1.7 : 0 }}
      >
        <strong>Readback:</strong> Nobody may unlock a door between 11pm and 6am.
      </motion.p>
      <motion.button
        type="button"
        tabIndex={-1}
        className="mt-3 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white"
        initial={false}
        animate={on ? { opacity: 1, scale: [1, 1, 0.94, 1] } : { opacity: 0, scale: 1 }}
        transition={{ delay: on ? 2.2 : 0, duration: 0.5 }}
      >
        Approve
      </motion.button>
    </Card>
  )
}

/* 5 ─ Evaluate */
const SCEN: [string, string, 'ALLOW' | 'DENY', 'ALLOW' | 'DENY'][] = [
  ['unlock_door at 14:00', 'resident, daytime', 'ALLOW', 'ALLOW'],
  ['unlock_door at 03:00', 'night rule', 'DENY', 'DENY'],
  ['unlock_door at 23:00', 'edge of night', 'DENY', 'DENY'],
  ['set_thermostat 21', 'within 16-28', 'ALLOW', 'ALLOW'],
  ['set_thermostat 35', 'outside 16-28', 'DENY', 'DENY'],
  ['open_valve 80%', 'over 50%', 'DENY', 'DENY'],
]
export function EvalVisual({ active }: V) {
  const { on } = useOn(active)
  return (
    <Card label="Scenario results table">
      <div className="space-y-1.5">
        {SCEN.map(([a, why, , res], i) => (
          <motion.div
            key={a}
            className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2"
            initial={false}
            animate={on ? { opacity: 1, rotateX: 0 } : { opacity: 0, rotateX: -80 }}
            transition={{ delay: on ? i * 0.15 : 0, duration: 0.35 }}
            style={{ transformPerspective: 600 }}
          >
            <div className="min-w-0">
              <p className="truncate font-mono text-xs font-semibold">{a}</p>
              <p className="text-xs text-slate-500">{why}</p>
            </div>
            <span className={`shrink-0 rounded px-2 py-0.5 text-xs font-bold ${res === 'ALLOW' ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}`}>{res}</span>
          </motion.div>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500">Illustrative scenarios. Studio generates and runs these through the engine.</p>
    </Card>
  )
}

/* 6 ─ Patch */
const DIFF: [' ' | '+' | '-', string][] = [
  [' ', '@mcp.tool()'],
  [' ', 'def unlock_door(door_id: str, pin=None):'],
  ['+', '    d = yog.check("agent", "can_unlock_door", door_id)'],
  ['+', '    if d.decision == "DENY":'],
  ['+', '        return f"blocked: {d.reason}"'],
  [' ', '    DOORS[door_id] = "unlocked"'],
]
export function PatchVisual({ active }: V) {
  const { on } = useOn(active)
  return (
    <Card label="Diff that adds yog.check to a tool">
      <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-xs leading-6">
        {DIFF.map(([k, l], i) => (
          <motion.div
            key={i}
            className={k === '+' ? 'bg-emerald-500/20 text-emerald-200' : 'text-slate-400'}
            initial={false}
            animate={on ? { opacity: 1, x: 0 } : { opacity: 0, x: k === '+' ? 30 : 0 }}
            transition={{ delay: on ? (k === '+' ? 0.5 + i * 0.2 : 0) : 0 }}
          >
            {k} {l}
          </motion.div>
        ))}
      </pre>
      <p className="mt-3 text-xs text-slate-500">Only the added lines change. The rest of your file is untouched.</p>
    </Card>
  )
}

/* 7 ─ Device (interactive) */
type Act = { label: string; call: (h: number) => Call }
const ACTS: Act[] = [
  { label: 'Unlock front door', call: (hour) => ({ tool: 'unlock_door', hour }) },
  { label: 'Set thermostat to 35°C', call: (hour) => ({ tool: 'set_thermostat', hour, temperature: 35 }) },
  { label: 'Set thermostat to 21°C', call: (hour) => ({ tool: 'set_thermostat', hour, temperature: 21 }) },
  { label: 'Open water main 80%', call: (hour) => ({ tool: 'open_valve', hour, percent: 80 }) },
]
const fmt = (h: number) => `${String(h).padStart(2, '0')}:00`

export function DeviceVisual() {
  const reduce = useReducedMotion()
  const [hour, setHour] = useState(14)
  const [locked, setLocked] = useState(true)
  const [res, setRes] = useState<{ n: number; text: string; r: ReturnType<typeof evaluate> } | null>(null)
  const [n, setN] = useState(0)

  function run(a: Act) {
    const r = evaluate(a.call(hour))
    const k = n + 1
    setN(k)
    setRes({ n: k, text: a.label, r })
    if (a.call(hour).tool === 'unlock_door') setLocked(r.decision === 'DENY' ? locked : false)
  }
  const denied = res?.r.decision === 'DENY'
  return (
    <Card label="Interactive smart home: try to unlock the door at different times">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Simulated device</p>
        <p className="font-mono text-sm" data-testid="clock">{fmt(hour)}</p>
      </div>
      <label className="mt-2 block text-xs text-slate-600">
        Clock
        <input
          type="range"
          min={0}
          max={23}
          value={hour}
          onChange={(e) => setHour(+e.target.value)}
          aria-label="Simulated hour"
          className="mt-1 w-full accent-sky-700"
        />
      </label>
      <div className="mt-3 flex items-center gap-4">
        <motion.div
          key={denied ? `shake${res?.n}` : 'still'}
          data-testid="door"
          data-state={locked ? 'locked' : 'unlocked'}
          className={`flex h-20 w-20 shrink-0 items-center justify-center rounded-xl text-3xl ${locked ? 'bg-slate-200' : 'bg-emerald-200'}`}
          animate={denied && !reduce ? { x: [0, -10, 10, -8, 8, -4, 4, 0] } : { x: 0 }}
          transition={{ duration: 0.5 }}
          aria-label={locked ? 'Door locked' : 'Door unlocked'}
        >
          {locked ? '🔒' : '🔓'}
        </motion.div>
        <div className="min-w-0 flex-1">
          <AnimatePresence mode="wait">
            {res ? (
              <motion.div key={res.n} initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                <DenyStamp decision={res.r.decision} id={res.n} />
                <p className="mt-2 text-sm text-slate-700" data-testid="reason">
                  {res.text}: {res.r.reason}.
                </p>
                <p className="font-mono text-xs text-slate-500">{res.r.rule}</p>
              </motion.div>
            ) : (
              <p className="text-sm text-slate-500">Drag the clock, then try an action.</p>
            )}
          </AnimatePresence>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2">
        {ACTS.map((a) => (
          <button key={a.label} type="button" onClick={() => run(a)} className="btn-secondary text-left text-xs" style={{ justifyContent: 'flex-start' }}>
            {a.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="mt-3 text-xs text-slate-500 underline"
        onClick={() => {
          setLocked(true)
          setRes(null)
          setHour(14)
        }}
      >
        Reset
      </button>
      <p className="mt-2 text-xs text-slate-500">This demo mirrors YOG’s rules in your browser. The real device page uses the real engine.</p>
    </Card>
  )
}
