import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { listPolicies } from '../api/policies'
import { HubSection } from '../components/hub/HubSection'
import { Reveal } from '../components/motion/Reveal'
import { Spotlight } from '../components/motion/Spotlight'
import { GROUPS, TOOLS, type StudioTool } from '../lib/tools'

function Badge({ status }: { status: StudioTool['status'] }) {
  return status === 'ready' ? (
    <span className="rounded-full border border-emerald-400/50 px-2 py-0.5 text-xs font-semibold text-emerald-300">Ready</span>
  ) : (
    <span className="rounded-full border border-white/25 px-2 py-0.5 text-xs font-semibold text-slate-300">Not built yet</span>
  )
}

function ToolCard({ t }: { t: StudioTool }) {
  return (
    <Spotlight as="li" className="flex h-full flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-xl font-bold" data-testid={`tool-name-${t.id}`}>{t.name}</h3>
        <Badge status={t.status} />
      </div>
      <p className="mt-1 text-slate-200">{t.purpose}</p>
      <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-glow">How it works</p>
      <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm text-slate-300">
        {t.how.map((s) => <li key={s}>{s}</li>)}
      </ol>
      <p className="mt-3 text-sm text-slate-400"><span className="font-semibold text-slate-300">It does not: </span>{t.limit}</p>
      <div className="mt-auto pt-5">
        {t.status === 'ready' ? (
          <Link to={t.to} className="btn-primary" data-testid={`tool-open-${t.id}`}>Open {t.name}</Link>
        ) : (
          <span className="text-sm text-slate-400" data-testid={`tool-soon-${t.id}`}>Planned. No page yet.</span>
        )}
      </div>
    </Spotlight>
  )
}

export default function StudioHubPage() {
  const { hash } = useLocation()
  const navigate = useNavigate()
  // Old share links were /studio#p=...; the workbench moved, so forward them with the program intact.
  useEffect(() => {
    if (hash.startsWith('#p=')) navigate(`/studio/workbench${hash}`, { replace: true })
  }, [hash, navigate])

  const ready = TOOLS.filter((t) => t.status === 'ready').length
  const planned = TOOLS.length - ready
  const [approvedId, setApprovedId] = useState<string | null>(null)
  useEffect(() => {
    listPolicies().then((p) => setApprovedId(p[0]?.id ?? null)).catch(() => undefined)
  }, [])
  return (
    <main>
      <HubSection status={
        <>
          <p data-testid="tool-count">{planned === 0 ? `${ready} tools, all ready.` : `${ready} ready, ${planned} planned.`}</p>
          {approvedId && (
            <p className="mt-1.5" data-testid="hub-approved">
              You have an approved policy ({approvedId.slice(-8)}). <Link to="/studio/scorecard" className="link">See its scorecard</Link>, or{' '}
              <Link to="/studio/map" className="link">draw its map</Link>.
            </p>
          )}
        </>
      } />
      <section id="all-tools" className="mx-auto max-w-6xl px-5 pb-2 pt-16" aria-labelledby="all-tools-title">
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-glow">Studio</p>
        <h2 id="all-tools-title" className="font-display max-w-3xl text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">Every tool, explained.</h2>
        <p className="mt-4 max-w-2xl text-lg text-slate-300">
          Every tool works on the same YOG policy. Use one on its own, or go left to right: build, understand, test, ship, operate.
        </p>
      </section>

      {GROUPS.map((g) => {
        const items = TOOLS.filter((t) => t.group === g.id)
        return (
          <section key={g.id} id={g.id} aria-labelledby={`g-${g.id}`} className="mx-auto max-w-6xl px-5 py-8">
            <Reveal>
              <h2 id={`g-${g.id}`} className="font-display text-2xl font-bold">{g.title}</h2>
              <p className="mt-1 text-slate-400">{g.blurb}</p>
            </Reveal>
            <ul className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-3" data-testid={`group-${g.id}`}>
              {items.map((t) => <ToolCard key={t.id} t={t} />)}
            </ul>
          </section>
        )
      })}
      <div className="pb-20" />
    </main>
  )
}
