import { useEffect, useMemo, useRef, useState } from 'react'

export interface Command { id: string; label: string; hint?: string; run: () => void }

/** Ctrl/Cmd+K: every action in the workbench, searchable. */
export function CommandPalette({ open, onClose, commands }: { open: boolean; onClose: () => void; commands: Command[] }) {
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const shown = useMemo(() => commands.filter((c) => c.label.toLowerCase().includes(q.toLowerCase())).slice(0, 12), [commands, q])
  useEffect(() => { if (open) { setQ(''); setSel(0); setTimeout(() => input.current?.focus(), 0) } }, [open])
  if (!open) return null
  const go = (c?: Command) => { if (c) { onClose(); c.run() } }
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-24" onMouseDown={onClose} data-testid="palette">
      <div className="w-full max-w-lg rounded-lg border border-slate-300 bg-white p-2 shadow-2xl" role="dialog" aria-label="Command palette" onMouseDown={(e) => e.stopPropagation()}>
        <input
          ref={input} value={q} onChange={(e) => { setQ(e.target.value); setSel(0) }} aria-label="Type a command"
          placeholder="Type a command…" className="field mb-2"
          onKeyDown={(e) => {
            if (e.key === 'Escape') onClose()
            if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, shown.length - 1)) }
            if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)) }
            if (e.key === 'Enter') go(shown[sel])
          }}
        />
        <ul role="listbox">
          {shown.map((c, i) => (
            <li key={c.id} role="option" aria-selected={i === sel}>
              <button type="button" className={`flex w-full justify-between rounded px-2 py-1.5 text-left text-sm ${i === sel ? 'bg-slate-200' : ''}`} onMouseEnter={() => setSel(i)} onClick={() => go(c)}>
                <span>{c.label}</span>{c.hint && <span className="text-xs text-slate-500">{c.hint}</span>}
              </button>
            </li>
          ))}
          {!shown.length && <li className="px-2 py-2 text-sm text-slate-500">No matching command.</li>}
        </ul>
      </div>
    </div>
  )
}

const STEPS = [
  { title: 'Write YOG on the left', body: 'Colours, completion (Ctrl+Space) and live error markers help as you type. Load any team example from the library.' },
  { title: 'See what the compiler sees', body: 'The tabs show the tokens, the syntax tree, the checks and a plain-English readback, updated as you type.' },
  { title: 'Test decisions', body: 'Add “# -> DENY” after a query to make it a test. Click a result to see exactly which clause decided it.' },
  { title: 'Draft rules from English', body: 'The Assist tab finds similar examples and drafts YOG. You always read it before it enters your program.' },
]

/** First-run guided tour. Skippable, and reopenable from the toolbar. */
export function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [i, setI] = useState(0)
  useEffect(() => { if (open) setI(0) }, [open])
  if (!open) return null
  const s = STEPS[i]
  return (
    <div className="fixed bottom-6 right-6 z-40 w-80 rounded-lg border border-sky-600 bg-white p-4 shadow-2xl" role="dialog" aria-label="Welcome tour" data-testid="tour">
      <div className="text-xs text-slate-500">Step {i + 1} of {STEPS.length}</div>
      <h3 className="mt-1 font-display text-base font-bold">{s.title}</h3>
      <p className="mt-1 text-sm text-slate-600">{s.body}</p>
      <div className="mt-3 flex items-center gap-2">
        <button type="button" className="text-sm text-slate-500 hover:text-slate-800" onClick={onClose} data-testid="tour-skip">Skip</button>
        <span className="flex-1" />
        {i > 0 && <button type="button" className="btn-secondary" onClick={() => setI(i - 1)}>Back</button>}
        <button type="button" className="btn-primary" onClick={() => (i === STEPS.length - 1 ? onClose() : setI(i + 1))} data-testid="tour-next">{i === STEPS.length - 1 ? 'Done' : 'Next'}</button>
      </div>
    </div>
  )
}
