import { useState } from 'react'
import { check, type CheckResult } from '../api/check'
import { ResultCard } from '../components/ResultCard'

const SAMPLE_POLICY = `fact role(alice, admin)
fact role(bob, viewer)
fact environment(db1, production)
fact environment(db2, staging)

rule is_prod(R):
    environment(R, production)

allow can_delete(User, Res):
    role(User, admin)

allow can_delete(User, Res):
    role(User, viewer)

deny can_delete(User, Res):
    is_prod(Res)
    not role(User, admin)
`

const inputCls = 'w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm'

export default function CheckPage() {
  const [policy, setPolicy] = useState(SAMPLE_POLICY)
  const [actor, setActor] = useState('bob')
  const [action, setAction] = useState('can_delete')
  const [resource, setResource] = useState('db1')
  const [context, setContext] = useState('')
  const [result, setResult] = useState<CheckResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const ctx = context.split('\n').map((s) => s.trim()).filter(Boolean)
      setResult(await check({ policy, actor, action, resource, context: ctx }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <section>
        <h2 className="mb-2 font-semibold">Policy (YOG)</h2>
        <textarea
          value={policy}
          onChange={(e) => setPolicy(e.target.value)}
          spellCheck={false}
          className="h-96 w-full rounded border border-slate-300 bg-white p-2 font-mono text-xs"
        />
      </section>
      <section className="space-y-3">
        <h2 className="font-semibold">Request</h2>
        <label className="block text-sm">Actor<input className={inputCls} value={actor} onChange={(e) => setActor(e.target.value)} /></label>
        <label className="block text-sm">Action (decision predicate)<input className={inputCls} value={action} onChange={(e) => setAction(e.target.value)} /></label>
        <label className="block text-sm">Resource<input className={inputCls} value={resource} onChange={(e) => setResource(e.target.value)} /></label>
        <label className="block text-sm">
          Context facts (one per line, e.g. <code>hour(now, 3)</code>)
          <textarea className={`${inputCls} h-16 font-mono`} value={context} onChange={(e) => setContext(e.target.value)} />
        </label>
        <button
          onClick={run}
          disabled={loading}
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? 'Checking…' : 'Check'}
        </button>
        {error && (
          <div className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900" role="alert">
            <b>Policy error:</b> {error}
          </div>
        )}
        {result && <ResultCard result={result} />}
      </section>
    </div>
  )
}
