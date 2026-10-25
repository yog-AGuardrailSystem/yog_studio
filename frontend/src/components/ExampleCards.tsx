import type { Retrieved } from '../api/retrieve'

export function ExampleCards({ examples }: { examples: Retrieved[] }) {
  if (examples.length === 0) return null
  return (
    <div className="grid gap-3 md:grid-cols-3" data-testid="example-cards">
      {examples.map((ex) => (
        <div key={ex.id} className="rounded border border-slate-200 bg-white p-3">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span className="font-mono">{ex.id}</span>
            <span title="cosine similarity">sim {ex.score.toFixed(2)}</span>
          </div>
          <p className="mt-1 text-sm font-medium">{ex.english}</p>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-indigo-700">Show YOG</summary>
            <pre className="mt-1 max-h-56 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">{ex.gold_yog}</pre>
          </details>
        </div>
      ))}
    </div>
  )
}
