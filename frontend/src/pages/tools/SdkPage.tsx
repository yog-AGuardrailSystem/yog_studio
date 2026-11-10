import { useEffect, useState } from 'react'
import { sdkRuntime, sdkTry, type TryResult } from '../../api/tools'
import { PolicyPicker, usePolicyChoice } from '../../components/tool/PolicyPicker'
import { DecisionPill, ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'

const SNIPPET = `from yog_runtime import yog_guard

@mcp.tool()                      # your framework's decorator stays on top
@yog_guard("unlock_door")        # the guard sits directly above def
def unlock_door(door_id: str):
    ...

# A denied call raises yog_runtime.YogDenied instead of running the tool.`

const ENV = `YOG_POLICY=policy.yog          # which policy file (default: next to yog_runtime.py)
YOG_POLICY_SHA256=<hash>       # refuse to run if the file is not exactly the approved one
YOG_NOW="3,sat"                # pin the clock for testing
YOG_LOG=decisions.jsonl        # write every decision, for Trace Replay
python yog_runtime.py --selftest`

export default function SdkPage() {
  const { choice, setChoice, policies } = usePolicyChoice()
  const [rt, setRt] = useState<{ source: string; lines: number } | null>(null)
  const [tool, setTool] = useState('unlock_door')
  const [args, setArgs] = useState('{"door_id": "front_door"}')
  const [hour, setHour] = useState(3)
  const [day, setDay] = useState('tue')
  const [out, setOut] = useState<TryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => { sdkRuntime().then(setRt).catch((e) => setError(msg(e))) }, [])

  async function tryIt() {
    setError(null)
    try {
      const parsed = JSON.parse(args || '{}')
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error('Arguments must be a JSON object, for example {"door_id": "front_door"}')
      setOut(await sdkTry(choice.ref, tool.trim(), parsed, hour, day))
    } catch (e) {
      setOut(null)
      setError(e instanceof SyntaxError ? 'The arguments are not valid JSON.' : msg(e))
    }
  }
  function download() {
    if (!rt) return
    const url = URL.createObjectURL(new Blob([rt.source], { type: 'text/x-python' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'yog_runtime.py'
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <ToolPage id="sdk">
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <section className="min-w-0 space-y-3 rounded border border-slate-200 bg-white p-3 text-sm">
          <h2 className="font-semibold">1. Put the guard in your agent</h2>
          <pre className="overflow-auto rounded bg-slate-50 p-2 font-mono text-xs" data-testid="sdk-snippet">{SNIPPET}</pre>
          <p>The <b>Patch agent</b> tool adds these lines for you. The guard needs three files next to your agent: <code>yog_runtime.py</code>, <code>yog.py</code> and <code>policy.yog</code>. <b>Export Pack</b> bundles all three.</p>
          <h2 className="font-semibold">2. Settings (environment variables)</h2>
          <pre className="overflow-auto rounded bg-slate-50 p-2 font-mono text-xs">{ENV}</pre>
          <h2 className="font-semibold">What it guarantees</h2>
          <ul className="list-disc space-y-0.5 pl-5">
            <li>Any error, missing file or odd input is a DENY. It never fails open.</li>
            <li>Decisions are taken one at a time, so two threads cannot see each other’s facts.</li>
            <li>The hash pin refuses a policy file that was edited after you approved it.</li>
          </ul>
          <div className="flex gap-2">
            <button type="button" className="rounded bg-sky-700 px-3 py-1.5 font-semibold text-on-accent disabled:opacity-50" onClick={download} disabled={!rt} data-testid="sdk-download">Download yog_runtime.py</button>
            <button type="button" className="rounded border border-slate-300 px-3 py-1.5 disabled:opacity-50" disabled={!rt} onClick={async () => { try { await navigator.clipboard.writeText(rt!.source); setCopied(true) } catch { setError('Copying was blocked by the browser; use Download.') } }}>{copied ? 'Copied' : 'Copy the code'}</button>
          </div>
        </section>
        <section className="min-w-0 space-y-3 rounded border border-slate-200 bg-white p-3 text-sm">
          <h2 className="font-semibold">Try a call</h2>
          <p className="text-xs text-slate-600">Ask what the guard would answer, using the same fact-building code the guard runs.</p>
          <PolicyPicker choice={choice} onChange={setChoice} policies={policies} />
          <div className="grid gap-2 sm:grid-cols-2">
            <label>Tool <input value={tool} onChange={(e) => setTool(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" data-testid="try-tool" /></label>
            <label>Arguments (JSON) <input value={args} onChange={(e) => setArgs(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1 font-mono text-xs" data-testid="try-args" /></label>
            <label>Hour <input type="number" min={0} max={23} value={hour} onChange={(e) => setHour(Number(e.target.value))} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" data-testid="try-hour" /></label>
            <label>Day <select value={day} onChange={(e) => setDay(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1">{['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map((d) => <option key={d}>{d}</option>)}</select></label>
          </div>
          <button type="button" className="rounded bg-sky-700 px-4 py-1.5 font-semibold text-on-accent" onClick={() => void tryIt()} data-testid="try-run">Ask the guard</button>
          <ErrorBox error={error} />
          {out && (
            <div className="rounded border border-slate-200 p-3" data-testid="try-result">
              <div className="flex items-center gap-2"><DecisionPill d={out.decision} /><span>{out.reason}</span></div>
              <p className="mt-2 font-mono text-xs">{out.action}(agent, {out.resource})</p>
              <p className="font-mono text-xs">facts: {out.context.join(', ')}</p>
              <p className="mt-1 text-xs text-slate-500">policy sha256 {out.policy_sha256.slice(0, 16)}… ({out.policy_label})</p>
            </div>
          )}
        </section>
      </div>
      {rt && (
        <details className="rounded border border-slate-200 bg-white p-3 text-sm">
          <summary className="cursor-pointer font-semibold">Read the whole module ({rt.lines} lines)</summary>
          <pre className="mt-2 max-h-96 overflow-auto rounded bg-slate-50 p-2 font-mono text-xs" data-testid="sdk-source">{rt.source}</pre>
        </details>
      )}
    </ToolPage>
  )
}
