import { useState } from 'react'
import { mutation, type MutationReport } from '../../api/tools'
import { PolicyPicker, usePolicyChoice } from '../../components/tool/PolicyPicker'
import { ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'
import { describeScenario, loadScenarios, saveScenarios } from '../../lib/myScenarios'

export default function StrengthPage() {
  const { choice, setChoice, policies } = usePolicyChoice()
  const [mine, setMine] = useState(loadScenarios())
  const [out, setOut] = useState<MutationReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      setOut(await mutation(choice.ref, mine))
    } catch (e) {
      setOut(null)
      setError(msg(e))
    } finally {
      setBusy(false)
    }
  }
  const tone = out?.score == null ? '' : out.score >= 90 ? 'text-green-800' : out.score >= 60 ? 'text-amber-800' : 'text-red-800'
  return (
    <ToolPage id="strength">
      <PolicyPicker choice={choice} onChange={setChoice} policies={policies} />
      <section className="rounded border border-slate-200 bg-white p-3 text-sm">
        <h2 className="font-semibold">The tests that will judge the policy</h2>
        {mine.length === 0 ? (
          <p className="text-slate-700">You have not saved any scenarios yet, so Studio will use probes it generates from the policy. That measures how sensitive those probes are. Save scenarios from the Red-Team page to score tests that come from your intent.</p>
        ) : (
          <>
            <p className="text-slate-700">{mine.length} scenario{mine.length === 1 ? '' : 's'} saved in this browser:</p>
            <ul className="mt-1 max-h-40 list-disc space-y-0.5 overflow-auto pl-5 font-mono text-xs" data-testid="mine-list">
              {mine.map((s, i) => <li key={i}>{describeScenario(s)} <button type="button" className="font-sans text-red-800 underline" onClick={() => { const n = mine.filter((_, k) => k !== i); setMine(n); saveScenarios(n) }}>remove</button></li>)}
            </ul>
          </>
        )}
        <button type="button" onClick={() => void run()} disabled={busy} className="mt-2 rounded bg-sky-700 px-4 py-1.5 font-semibold text-on-accent disabled:opacity-50" data-testid="strength-run">{busy ? 'Breaking the policy…' : 'Measure test strength'}</button>
      </section>
      <ErrorBox error={error} />
      {out && (
        <div className="space-y-3" data-testid="strength-result">
          <div className="flex flex-wrap items-center gap-6 rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-center">
              <div className={`font-display text-4xl font-extrabold ${tone}`} data-testid="strength-score">{out.score === null ? 'n/a' : `${out.score}%`}</div>
              <div className="text-xs text-slate-600">of breaking changes noticed</div>
            </div>
            <div className="text-sm">
              <b>{out.killed}</b> noticed, <b data-testid="strength-survived">{out.survived}</b> not noticed, <b>{out.invalid}</b> did not compile<br />
              judged by {out.tests_used} {out.tests_source === 'yours' ? 'of your scenarios' : 'generated probes'}{out.tests_excluded ? `, ${out.tests_excluded} skipped because the unchanged policy already fails them` : ''}
            </div>
            <p className="basis-full text-xs text-slate-600">{out.note}</p>
          </div>
          <div className="max-h-[30rem] overflow-auto rounded border border-slate-200 bg-white">
            <table className="w-full text-left text-xs" data-testid="mutants">
              <thead className="sticky top-0 bg-slate-100 text-slate-600"><tr><th className="p-2">Result</th><th>Line</th><th>Change</th><th>Before → after</th><th>Noticed by</th></tr></thead>
              <tbody>
                {[...out.mutants].sort((a, b) => (a.status === 'survived' ? -1 : 1) - (b.status === 'survived' ? -1 : 1)).map((m) => (
                  <tr key={m.id} className="border-t border-slate-100 align-top" data-status={m.status}>
                    <td className={`p-2 font-bold ${m.status === 'survived' ? 'text-red-800' : m.status === 'killed' ? 'text-green-800' : 'text-slate-500'}`}>{m.status === 'survived' ? 'NOT noticed' : m.status === 'killed' ? 'noticed' : 'invalid'}</td>
                    <td>{m.line}</td><td>{m.description}</td>
                    <td className="font-mono">{m.before} → {m.after}</td>
                    <td className="font-mono">{m.caught_by ?? '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </ToolPage>
  )
}
