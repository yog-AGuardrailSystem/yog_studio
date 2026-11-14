import { motion } from 'motion/react'
import { Link } from "react-router-dom"
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  compile, runProgram, teamExamples,
  type CompileInfo, type RunResponse, type TeamGroup,
} from '../api/compile'
import { YogEditor } from '../components/YogEditor'
import { AiModeToggle, useAiMode } from '../lib/aiMode'
import { CommandPalette, Tour, type Command } from '../components/workbench/Overlays'
import {
  AssistPanel, AstPanel, BenchmarkPanel, CIRPanel, CLexerPanel, ChecksPanel, ReadbackPanel, TestsPanel, TokensPanel,
} from '../components/workbench/Panels'
import {
  STARTER, decisionPredicates, downloadText, safeGet, safeSet, shareUrl, sourceFromHash, traceLines,
} from '../lib/workbench'

const TABS = ['Checks', 'Tests', 'Tokens', 'AST', 'Readback', 'C lexer', 'C IR', 'Assist', 'Evidence'] as const
type Tab = (typeof TABS)[number]
const SRC_KEY = 'yog.workbench.source'
const TOUR_KEY = 'yog.workbench.tour'

export default function WorkbenchPage() {
  const [source, setSource] = useState<string>(() => sourceFromHash(location.hash) ?? safeGet(SRC_KEY) ?? STARTER)
  const [tab, setTab] = useState<Tab>('Checks')
  const [info, setInfo] = useState<CompileInfo | null>(null)
  const [run, setRun] = useState<RunResponse | null>(null)
  const [groups, setGroups] = useState<TeamGroup[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [adhoc, setAdhoc] = useState({ actor: 'alice', action: 'can_delete', resource: 'db1', context: '' })
  const [why, setWhy] = useState<{ reason: string; trace: string[] } | null>(null)
  const [palette, setPalette] = useState(false)
  const [tour, setTour] = useState(() => safeGet(TOUR_KEY) !== 'done')
  const [toast, setToast] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const editor = useRef<{ focusLine: (n: number) => void } | null>(null)
  const seq = useRef(0)

  const ai = useAiMode()
  useEffect(() => { teamExamples().then(setGroups).catch((e) => setLoadError(e instanceof Error ? e.message : String(e))) }, [])

  // autosave + debounced live compile
  useEffect(() => {
    safeSet(SRC_KEY, source)
    const mine = ++seq.current
    setBusy(true)
    const t = setTimeout(async () => {
      try {
        const c = await compile(source)
        if (mine !== seq.current) return
        setInfo(c)
        const preds = decisionPredicates(c.predicates)
        const a = preds.includes(adhoc.action) || !preds.length ? adhoc : { ...adhoc, action: preds[0] }
        const ctx = a.context.split('\n').map((s) => s.trim()).filter(Boolean)
        const r = await runProgram(source, c.ok && a.actor && a.resource ? { actor: a.actor, action: a.action, resource: a.resource, context: ctx } : undefined)
        if (mine === seq.current) { setRun(r); if (a !== adhoc) setAdhoc(a) }
      } catch (e) {
        if (mine === seq.current) setLoadError(e instanceof Error ? e.message : String(e))
      } finally {
        if (mine === seq.current) setBusy(false)
      }
    }, 350)
    return () => clearTimeout(t)
  }, [source, adhoc.actor, adhoc.action, adhoc.resource, adhoc.context]) // eslint-disable-line react-hooks/exhaustive-deps

  const flash = useCallback((m: string) => { setToast(m); setTimeout(() => setToast(null), 2200) }, [])
  const closeTour = () => { setTour(false); safeSet(TOUR_KEY, 'done') }

  const hi = useMemo(() => (why ? traceLines(source, why.reason, why.trace) : { deciding: null, support: [] }), [why, source])
  const diagnostics = info?.diagnostics ?? []

  function load(g: TeamGroup) {
    const known = groups.some((x) => x.source === source) || source === STARTER
    if (!known && source.trim() && !window.confirm('Replace what is in the editor with this example? (Your current text is kept in your browser until you edit again; use Ctrl+Z to undo.)')) return
    setSource(g.source); setWhy(null); setTab('Tests')
    const q = g.source.match(/^query\s+(\w+)\((\w+),\s*(\w+)\)/m)
    if (q) setAdhoc({ action: q[1], actor: q[2], resource: q[3], context: '' })
  }
  async function copyShare() {
    const url = shareUrl(source)
    try { await navigator.clipboard.writeText(url); flash('Link copied') } catch { flash('Copy failed: ' + url.slice(0, 40) + '…') }
    history.replaceState(null, '', url.replace(location.origin, ''))
  }
  const insert = (yog: string) => { setSource((s) => s.replace(/\s*$/, '\n\n') + yog.trim() + '\n'); flash('Added to your program'); setTab('Checks') }

  const commands: Command[] = [
    ...TABS.map((t) => ({ id: 'tab-' + t, label: `Show ${t} tab`, run: () => setTab(t) })),
    { id: 'share', label: 'Copy share link', hint: 'program in the URL', run: copyShare },
    { id: 'dl', label: 'Download as .yog', run: () => downloadText('policy.yog', source) },
    { id: 'copy', label: 'Copy program', run: () => { void navigator.clipboard?.writeText(source); flash('Copied') } },
    { id: 'new', label: 'New empty program', run: () => { setSource('# New YOG program\n'); setWhy(null) } },
    { id: 'starter', label: 'Load the starter program', run: () => setSource(STARTER) },
    { id: 'tour', label: 'Show the welcome tour', run: () => setTour(true) },
    ...groups.map((g) => ({ id: 'ex-' + g.id, label: `Load example ${g.id}: ${g.title}`, run: () => load(g) })),
  ]

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); e.stopPropagation(); setPalette((p) => !p) }
    }
    window.addEventListener('keydown', onKey, true) // capture: Monaco would otherwise swallow Ctrl+K as a chord prefix
    return () => window.removeEventListener('keydown', onKey, true)
  }) // eslint-disable-line react-hooks/exhaustive-deps

  const errCount = diagnostics.filter((d) => d.severity === 'error').length
  const tabLabel = (t: Tab) => (t === 'Checks' && info ? (info.ok ? 'Checks ✓' : `Checks (${errCount})`) : t === 'Tests' && run?.ok ? `Tests ${run.passed}/${run.passed + run.failed}` : t)

  return (
    <div data-testid="workbench">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h1 className="font-display text-xl font-bold">YOG workbench</h1>
        <span className={`compile-ring ${busy ? 'is-busy' : ''}`} aria-hidden data-motion="wb:compile-ring" title={busy ? 'Compiling…' : 'Up to date'} />
        {ai.mode === 'offline' && <span className="chip" data-testid="offline-chip" title="No AI model is used; Assist copies the nearest example">Offline demo mode</span>}
        {ai.info?.engine === 'c' && <span className="chip" data-testid="engine-chip" title={ai.info.engine_roles}>Engine: C</span>}
        <span className="flex-1" />
        <AiModeToggle compact />
        <button type="button" className="btn-secondary" onClick={() => setPalette(true)} data-testid="open-palette">Commands <kbd className="ml-1 text-xs text-slate-400">Ctrl K</kbd></button>
        <button type="button" className="btn-secondary" onClick={copyShare} data-testid="share">Share link</button>
        <button type="button" className="btn-secondary" onClick={() => downloadText('policy.yog', source)}>Download .yog</button>
        <button type="button" className="btn-secondary" onClick={() => setTour(true)}>Tour</button>
        <Link className="btn-secondary" to="/agent">Agent tools →</Link>
      </div>
      {loadError && <p className="mb-3 rounded border border-amber-600 bg-amber-50 p-2 text-sm text-amber-900" role="alert">{loadError}</p>}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[220px_minmax(0,1.15fr)_minmax(0,1fr)]">
        <aside aria-label="Example library" className="max-h-[640px] overflow-auto rounded border border-slate-200 bg-white p-2" data-testid="library">
          <h2 className="px-1 pb-1 text-sm font-semibold">Examples</h2>
          <p className="px-1 pb-2 text-xs text-slate-500">The engine team’s groups A–R.</p>
          <ul>
            {groups.map((g) => (
              <li key={g.id}>
                <button type="button" onClick={() => load(g)} data-testid={`example-${g.id.replace('/', '')}`}
                  className={`w-full rounded px-2 py-1.5 text-left text-sm hover:bg-slate-200 ${g.source === source ? 'bg-slate-200' : ''}`} title={g.english}>
                  <span className="font-mono text-xs text-sky-600">{g.id}</span> {g.title}
                </button>
              </li>
            ))}
          </ul>
          {!groups.length && !loadError && <p className="px-1 text-xs text-slate-500">Loading…</p>}
        </aside>
        <section aria-label="Editor">
          <YogEditor value={source} onChange={(v) => { setSource(v); setWhy(null) }} diagnostics={diagnostics}
            decidingLine={hi.deciding} supportLines={hi.support} onReady={(api) => (editor.current = api)} />
          <p className="mt-1 text-xs text-slate-500">Autosaved in this browser. Ctrl+Space for completions, Ctrl+K for every command.</p>
        </section>
        <section aria-label="Compiler output">
          <div role="tablist" className="mb-3 flex flex-wrap gap-1 border-b border-slate-200">
            {TABS.map((t) => (
              <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => setTab(t)} data-testid={`tab-${t.replace(' ', '-')}`}
                className={`relative px-3 py-1.5 text-sm ${tab === t ? 'font-semibold text-slate-900' : 'text-slate-600 hover:text-slate-900'}`}>
                {tabLabel(t)}
                {tab === t && <motion.span layoutId="wb-tabline" className="absolute inset-x-0 -bottom-px h-0.5 bg-sky-500" data-motion="wb:tabline" />}
              </button>
            ))}
          </div>
          <div role="tabpanel" className="max-h-[560px] overflow-auto pr-1">
            {tab === 'Checks' && <ChecksPanel info={info} source={source} onFix={(n) => { setSource(n); flash('Fixed') }} onJump={(l) => editor.current?.focusLine(l)} />}
            {tab === 'Tests' && <TestsPanel run={run} source={source} decisions={decisionPredicates(info?.predicates ?? [])} adhoc={adhoc} setAdhoc={setAdhoc} onWhy={setWhy} why={why ? why.reason : null} />}
            {tab === 'Tokens' && <TokensPanel info={info} />}
            {tab === 'AST' && <AstPanel info={info} />}
            {tab === 'Readback' && <ReadbackPanel source={source} ok={!!info?.ok} />}
            {tab === 'C lexer' && <CLexerPanel source={source} available={!!ai.info?.c_lexer} />}
            {tab === 'C IR' && <CIRPanel source={source} available={!!ai.info?.c_ir} />}
            {tab === 'Assist' && <AssistPanel current={source} onInsert={insert} onReplace={(y) => { setSource(y); setTab('Checks') }} />}
            {tab === 'Evidence' && <BenchmarkPanel />}
          </div>
        </section>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} commands={commands} />
      <Tour open={tour} onClose={closeTour} />
      <div aria-live="polite" className="fixed bottom-4 left-1/2 -translate-x-1/2">{toast && <div className="pop-in rounded bg-slate-900 px-3 py-1.5 text-sm text-white shadow-lg" data-testid="toast" data-motion="wb:toast">{toast}</div>}</div>
    </div>
  )
}
