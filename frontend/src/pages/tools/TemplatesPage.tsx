import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { combineTemplates, templates, type CombineResult, type Template } from '../../api/tools'
import { ErrorBox, msg, ToolPage } from '../../components/tool/ToolPage'
import { shareUrl } from '../../lib/workbench'
import { useAppState } from '../../state'

export default function TemplatesPage() {
  const { rules, setRules } = useAppState()
  const [all, setAll] = useState<Template[] | null>(null)
  const [q, setQ] = useState('')
  const [pack, setPack] = useState('all')
  const [picked, setPicked] = useState<string[]>([])
  const [combo, setCombo] = useState<CombineResult | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [added, setAdded] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { templates().then(setAll).catch((e) => setError(msg(e))) }, [])
  const packs = useMemo(() => [...new Map((all ?? []).map((t) => [t.pack, t.pack_title])).entries()], [all])
  const shown = (all ?? []).filter((t) => (pack === 'all' || t.pack === pack) && (!q || (t.english + t.id + t.tools_context.join(' ')).toLowerCase().includes(q.toLowerCase())))

  function toggle(id: string) {
    setCombo(null)
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length >= 6 ? p : [...p, id]))
  }
  async function combine() {
    setError(null)
    try { setCombo(await combineTemplates(picked)) } catch (e) { setError(msg(e)) }
  }
  function addRule(t: Template) {
    const cur = rules.filter((r) => r.trim())
    if (!cur.includes(t.english)) setRules([...cur, t.english])
    setAdded(t.id)
  }

  return (
    <ToolPage id="templates">
      <div className="flex flex-wrap items-center gap-3 rounded border border-slate-200 bg-white p-3 text-sm">
        <label>Search <input value={q} onChange={(e) => setQ(e.target.value)} className="ml-1 rounded border border-slate-300 px-2 py-1" data-testid="tpl-search" /></label>
        <label>Pack <select value={pack} onChange={(e) => setPack(e.target.value)} className="ml-1 rounded border border-slate-300 px-1 py-1" data-testid="tpl-pack">
          <option value="all">all</option>{packs.map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>
        <span className="text-xs text-slate-500" data-testid="tpl-count">{shown.length} of {all?.length ?? 0} templates</span>
      </div>
      <ErrorBox error={error} />
      {picked.length > 0 && (
        <div className="rounded border border-sky-300 bg-sky-50 p-3 text-sm text-slate-900" data-testid="tpl-combine">
          <b>{picked.length}</b> selected (up to 6). <button type="button" className="ml-2 rounded bg-sky-700 px-3 py-1 font-semibold text-on-accent" onClick={() => void combine()} data-testid="tpl-combine-go">Combine and check</button>
          <button type="button" className="ml-2 underline" onClick={() => { setPicked([]); setCombo(null) }}>Clear</button>
          {combo && (combo.ok ? (
            <div className="mt-2" data-testid="tpl-combined">
              <p className="font-semibold text-green-800">The engine accepts the combination.</p>
              <pre className="mt-1 max-h-60 overflow-auto rounded bg-white p-2 font-mono text-xs">{combo.source}</pre>
              <a className="mt-1 inline-block text-link underline" href={shareUrl(combo.source)}>Open it in the workbench</a>
            </div>
          ) : <p className="mt-2 text-red-800" role="alert" data-testid="tpl-combine-error">These do not combine: {combo.errors.join('; ')}</p>)}
        </div>
      )}
      <ul className="grid gap-3 md:grid-cols-2" data-testid="tpl-list">
        {shown.map((t) => (
          <li key={t.id} className="min-w-0 rounded border border-slate-200 bg-white p-3 text-sm" data-testid={`tpl-${t.id}`}>
            <div className="flex items-start gap-2">
              <input type="checkbox" checked={picked.includes(t.id)} onChange={() => toggle(t.id)} aria-label={`Select ${t.id}`} className="mt-1" />
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{t.english}</p>
                <p className="mt-0.5 text-xs text-slate-500">{t.pack_title} · {t.id} · {t.scenarios} test scenarios{t.tools_context.length ? ' · ' + t.tools_context.join(', ') : ''}</p>
                {!t.reviewed && <p className="mt-1 text-xs font-semibold text-amber-800">Draft: the team has not reviewed this one yet.</p>}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs">
              <button type="button" className="text-link underline" onClick={() => setOpen(open === t.id ? null : t.id)} aria-expanded={open === t.id}>{open === t.id ? 'Hide' : 'Show'} the YOG</button>
              <a className="text-link underline" href={shareUrl(t.yog)}>Open in the workbench</a>
              <button type="button" className="text-link underline" onClick={() => addRule(t)}>Add as one of my rules</button>
              {added === t.id && <span className="text-green-800">Added. <Link to="/rules" className="underline">Go to Rules</Link></span>}
            </div>
            {open === t.id && <pre className="mt-2 max-h-56 overflow-auto rounded bg-slate-50 p-2 font-mono text-xs">{t.yog}</pre>}
          </li>
        ))}
      </ul>
    </ToolPage>
  )
}
