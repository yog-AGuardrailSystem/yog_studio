import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { PageIntro } from '../PageIntro'
import { TOOLS } from '../../lib/tools'

/** The frame every Studio tool page shares: a title, one line of purpose, and a collapsible "how it works / what it does not do". */
export function ToolPage({ id, children, intro }: { id: string; children: ReactNode; intro?: ReactNode }) {
  const tool = TOOLS.find((t) => t.id === id)
  const [open, setOpen] = useState(false)
  if (!tool) return <>{children}</>
  return (
    <div className="space-y-4" data-testid={`tool-page-${id}`}>
      <div className="flex items-start justify-between gap-3">
        <PageIntro step="Studio tool" title={tool.name}>{intro ?? tool.purpose}</PageIntro>
        <Link to="/studio" className="shrink-0 text-sm text-link underline">All tools</Link>
      </div>
      <div className="rounded border border-slate-200 bg-white p-3 text-sm">
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="font-semibold text-link" data-testid="how-toggle">
          {open ? 'Hide' : 'Show'}: how it works
        </button>
        {open && (
          <div className="mt-2" data-testid="how-body">
            <ol className="list-decimal space-y-1 pl-5">{tool.how.map((s) => <li key={s}>{s}</li>)}</ol>
            <p className="mt-2 text-slate-600"><b>It does not: </b>{tool.limit}</p>
          </div>
        )}
      </div>
      {children}
    </div>
  )
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert" data-testid="tool-error">{error}</div> : null
}

export const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))

/** A decision pill. Colour is never the only signal: the word is always shown. */
export function DecisionPill({ d }: { d: string }) {
  const cls = d === 'ALLOW' ? 'bg-green-100 text-green-800' : d === 'DENY' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-900'
  return <span className={`rounded px-1.5 py-0.5 text-xs font-bold ${cls}`}>{d}</span>
}

/** A policy listing with line numbers; `marks` are 1-based lines to highlight (and optionally click). */
export function PolicyLines({ source, marks = [], onLine }: { source: string; marks?: number[]; onLine?: (n: number) => void }) {
  const lines = source.split('\n')
  if (lines[lines.length - 1] === '') lines.pop()
  return (
    <pre className="max-h-96 overflow-auto rounded border border-slate-200 bg-slate-50 p-2 font-mono text-xs leading-5" data-testid="policy-lines">
      {lines.map((ln, i) => (
        <div key={i} className={marks.includes(i + 1) ? 'bg-amber-100 text-amber-900' : ''} data-testid={marks.includes(i + 1) ? 'line-marked' : undefined}
          onClick={onLine ? () => onLine(i + 1) : undefined}>
          <span className="mr-3 inline-block w-7 select-none text-right text-slate-500">{i + 1}</span>{ln || ' '}
        </div>
      ))}
    </pre>
  )
}
