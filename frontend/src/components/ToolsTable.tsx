import type { Tool } from '../api/types'

const HINT_STYLE: Record<string, string> = {
  deletes: 'bg-red-100 text-red-800',
  actuates: 'bg-orange-100 text-orange-800',
  network: 'bg-blue-100 text-blue-800',
  filesystem: 'bg-yellow-100 text-yellow-800',
  database: 'bg-purple-100 text-purple-800',
  shell: 'bg-rose-100 text-rose-800',
  financial: 'bg-emerald-100 text-emerald-800',
}

export function HintChip({ hint }: { hint: string }) {
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${HINT_STYLE[hint] ?? 'bg-slate-100 text-slate-700'}`}>{hint}</span>
}

interface Props {
  tools: Tool[]
  onSelect?: (t: Tool) => void
  /** If provided, renders a checkbox column (manual picking for `unknown` files). */
  selected?: Set<string>
  onToggle?: (name: string) => void
}

export function ToolsTable({ tools, onSelect, selected, onToggle }: Props) {
  if (tools.length === 0) return <p className="text-sm text-slate-500">No tools found.</p>
  return (
    <table className="w-full text-left text-sm" data-testid="tools-table">
      <thead className="border-b border-slate-300 text-xs uppercase text-slate-500">
        <tr>
          {selected && <th className="w-8 py-1" />}
          <th className="py-1">Tool</th>
          <th>Parameters</th>
          <th>Side-effect hints</th>
          <th className="text-right">Line</th>
        </tr>
      </thead>
      <tbody>
        {tools.map((t) => (
          <tr key={t.name} className="cursor-pointer border-b border-slate-100 align-top hover:bg-indigo-50" onClick={() => onSelect?.(t)}>
            {selected && (
              <td className="py-2" onClick={(e) => e.stopPropagation()}>
                <input type="checkbox" checked={selected.has(t.name)} onChange={() => onToggle?.(t.name)} aria-label={`select ${t.name}`} />
              </td>
            )}
            <td className="py-2 pr-3">
              <div className="font-mono font-semibold">{t.name}</div>
              {t.docstring && <div className="max-w-xs text-xs text-slate-500">{t.docstring}</div>}
            </td>
            <td className="py-2 pr-3 font-mono text-xs">
              {t.params.length === 0 ? (
                <span className="text-slate-400">—</span>
              ) : (
                t.params.map((p) => (
                  <div key={p.name}>
                    {p.name}
                    {p.type_hint && <span className="text-slate-500">: {p.type_hint}</span>}
                    {p.default !== null && <span className="text-slate-400"> = {p.default}</span>}
                  </div>
                ))
              )}
            </td>
            <td className="py-2">
              <div className="flex flex-wrap gap-1">
                {t.side_effect_hints.length === 0 ? <span className="text-xs text-slate-400">none</span> : t.side_effect_hints.map((h) => <HintChip key={h} hint={h} />)}
              </div>
            </td>
            <td className="py-2 text-right text-xs text-slate-500">{t.source_line}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
