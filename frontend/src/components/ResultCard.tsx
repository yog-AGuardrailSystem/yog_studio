import type { CheckResult } from '../api/check'

export function DecisionBadge({ decision }: { decision: 'ALLOW' | 'DENY' }) {
  const cls =
    decision === 'ALLOW'
      ? 'bg-green-100 text-green-800 border-green-300'
      : 'bg-red-100 text-red-800 border-red-300'
  return <span className={`inline-block rounded border px-2 py-0.5 text-xs font-bold ${cls}`}>{decision}</span>
}

export function ResultCard({ result }: { result: CheckResult }) {
  const allow = result.decision === 'ALLOW'
  return (
    <div
      className={`rounded-lg border-2 p-4 ${allow ? 'border-green-400 bg-green-50' : 'border-red-400 bg-red-50'}`}
      data-testid="result-card"
    >
      <div className={`text-3xl font-extrabold ${allow ? 'text-green-700' : 'text-red-700'}`}>{result.decision}</div>
      <p className="mt-1 text-sm text-slate-700">{result.reason}</p>
      {result.trace.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-slate-600">Trace ({result.trace.length} steps)</summary>
          <pre className="mt-2 max-h-72 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
            {result.trace.join('\n')}
          </pre>
        </details>
      )}
    </div>
  )
}
