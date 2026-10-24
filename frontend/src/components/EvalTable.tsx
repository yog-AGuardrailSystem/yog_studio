import type { EvalReport, ScenarioResult } from '../api/evaluate'
import { DecisionBadge } from './ResultCard'

interface Props {
  report: EvalReport
  onConfirm: (r: ScenarioResult) => void
  onFlip: (r: ScenarioResult) => void
}

export function EvalTable({ report, onConfirm, onFlip }: Props) {
  const s = report.summary
  return (
    <div className="space-y-3" data-testid="eval-report">
      <div className="flex flex-wrap items-center gap-4 text-sm">
        {s.pass_pct === null ? (
          <span className="font-semibold text-amber-700">No independent scenarios to grade against</span>
        ) : (
          <span className={`font-bold ${s.all_green ? 'text-green-700' : 'text-red-700'}`} data-testid="eval-score">
            {s.independent_passed}/{s.independent_total} independent scenarios pass ({s.pass_pct}%)
          </span>
        )}
        <span className="text-slate-500">{s.unconfirmed} unconfirmed probes (not counted)</span>
        {s.errors > 0 && <span className="text-red-700">{s.errors} row error(s)</span>}
      </div>

      {report.warnings.length > 0 && (
        <ul className="rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
          {report.warnings.map((w) => <li key={w}>⚠ {w}</li>)}
        </ul>
      )}

      <div className="max-h-96 overflow-auto rounded border border-slate-200 bg-white">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-100 uppercase text-slate-500">
            <tr>
              <th className="p-2">Action</th><th>Actor → resource</th><th>Context</th><th>Expected</th><th>Actual</th><th>Reason</th><th />
            </tr>
          </thead>
          <tbody>
            {report.results.map((r, i) => {
              const tone = r.error ? 'bg-amber-50' : r.unconfirmed ? 'bg-slate-50' : r.passed ? 'bg-green-50' : 'bg-red-50'
              return (
                <tr key={i} className={`border-t border-slate-100 align-top ${tone}`}>
                  <td className="p-2 font-mono">{r.action}</td>
                  <td className="font-mono">{r.actor} → {r.resource}</td>
                  <td className="font-mono">{r.context.join(', ') || '—'}<div className="text-slate-400">{r.note}</div></td>
                  <td>{r.unconfirmed ? <span className="text-slate-400">unconfirmed</span> : <DecisionBadge decision={r.expected} />}</td>
                  <td>{r.actual ? <DecisionBadge decision={r.actual} /> : <span className="text-red-700">error</span>}</td>
                  <td className="max-w-xs">{r.error ?? r.reason}</td>
                  <td className="whitespace-nowrap p-2">
                    {r.unconfirmed && !r.error && (
                      <>
                        <button className="mr-2 text-green-700 underline" onClick={() => onConfirm(r)}>confirm</button>
                        <button className="text-red-700 underline" onClick={() => onFlip(r)}>flip</button>
                      </>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
