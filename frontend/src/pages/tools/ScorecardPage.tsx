import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { scorecard, type Scorecard } from '../../api/tools'
import { PolicyPicker, usePolicyChoice } from '../../components/tool/PolicyPicker'
import { ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'
import { useAppState } from '../../state'

const TONE: Record<string, string> = {
  good: 'border-green-300 bg-green-50 text-green-800',
  warn: 'border-amber-300 bg-amber-50 text-amber-900',
  bad: 'border-red-300 bg-red-50 text-red-800',
  todo: 'border-slate-300 bg-white text-slate-800',
}
const WORD: Record<string, string> = { good: 'Good', warn: 'Look at this', bad: 'Problem', todo: 'Not measured' }

export default function ScorecardPage() {
  const { tools } = useAppState()
  const { choice, setChoice, policies } = usePolicyChoice()
  const [out, setOut] = useState<Scorecard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let alive = true
    setBusy(true)
    setError(null)
    scorecard(choice.ref, tools.map((t) => t.name))
      .then((s) => alive && setOut(s))
      .catch((e) => { if (alive) { setOut(null); setError(msg(e)) } })
      .finally(() => alive && setBusy(false))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [choice])

  return (
    <ToolPage id="scorecard">
      <PolicyPicker choice={choice} onChange={setChoice} policies={policies} />
      <ErrorBox error={error} />
      {busy && <p className="text-sm text-slate-600" role="status">Running the checks…</p>}
      {out && !busy && (
        <div className="space-y-3" data-testid="scorecard-result">
          <p className="font-display text-xl font-bold" data-testid="scorecard-headline">{out.headline}.</p>
          <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {out.metrics.map((m) => (
              <li key={m.id} className={`rounded-xl border p-4 ${TONE[m.status]}`} data-testid={`metric-${m.id}`} data-status={m.status}>
                <p className="text-xs font-semibold uppercase tracking-wide opacity-80">{m.label} · {WORD[m.status]}</p>
                <p className="font-display mt-1 text-2xl font-extrabold">{m.value ?? 'not measured'}</p>
                <p className="mt-1 text-sm">{m.detail}</p>
                <Link to={m.link} className="mt-2 inline-block text-sm underline">Open the tool</Link>
              </li>
            ))}
          </ul>
          <p className="text-xs text-slate-600">{out.policy_label}. A good score is not a proof of safety.</p>
        </div>
      )}
    </ToolPage>
  )
}
