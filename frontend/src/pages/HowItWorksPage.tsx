import { motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Reveal } from '../components/motion/Reveal'
import { useIsDesktop } from '../components/motion/useIsDesktop'
import {
  DeviceVisual,
  EvalVisual,
  PatchVisual,
  ToolsVisual,
  TranslateVisual,
  UploadVisual,
  VerifyVisual,
} from '../components/motion/visuals'

const STAGES = [
  { id: 'upload', short: 'Upload', title: 'Drop in your agent', text: 'Upload a Python agent or MCP server. The detector tells you what it found and shows the exact lines that prove it. If it is unsure, it says so and lets you pick the functions yourself. Your code is only read, never run.', Visual: UploadVisual },
  { id: 'tools', short: 'Tools', title: 'See what it can do', text: 'Each tool the agent can call is listed with its parameters and hints about its side effects, like “deletes” or “network”. These are the actions your rules will control.', Visual: ToolsVisual },
  { id: 'translate', short: 'Rules', title: 'Say it in English', text: 'Write the rule the way you would say it. Studio looks up similar example policies and an LLM drafts the YOG. The model only drafts. It never decides.', Visual: TranslateVisual },
  { id: 'verify', short: 'Verify', title: 'The engine checks, you approve', text: 'The YOG engine checks every draft. If it finds an error, the error goes back to the model for another try, up to three. Then you read the policy back in plain English and click Approve. Nothing goes live without that click.', Visual: VerifyVisual },
  { id: 'evaluate', short: 'Test', title: 'Test it on scenarios', text: 'Studio generates test cases, runs them through the engine and shows green ALLOW and red DENY, each with a reason and a trace. You see the policy behave before it is used.', Visual: EvalVisual },
  { id: 'patch', short: 'Patch', title: 'Get a minimal patch', text: 'Studio shows a side-by-side diff that wraps each tool call in yog.check(). It changes only the lines it must. It does not rewrite your file.', Visual: PatchVisual },
  { id: 'device', short: 'Try it', title: 'Watch YOG block a command', text: 'This one is live. Drag the clock to 3am and try to unlock the door. Then move it to noon and try again. The same input always gives the same answer.', Visual: DeviceVisual },
] as const

export default function HowItWorksPage() {
  const isDesktop = useIsDesktop()
  const [active, setActive] = useState(0)
  const refs = useRef<(HTMLElement | null)[]>([])

  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.i))
      },
      { rootMargin: '-45% 0px -45% 0px' },
    )
    refs.current.forEach((el) => el && io.observe(el))
    return () => io.disconnect()
  }, [isDesktop])

  const go = (i: number) => refs.current[i]?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' })
  const ActiveVisual = STAGES[active].Visual

  return (
    <main>
      <section className="mx-auto max-w-6xl px-5 pb-6 pt-14">
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-glow">How it works</p>
        <h1 className="font-display max-w-3xl text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
          From a Python agent to a policy that blocks the wrong action.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-slate-300">Scroll through the seven steps. The last one is yours to try.</p>
      </section>

      <nav aria-label="Steps" className="sticky top-14 z-10 border-y border-white/10 bg-slate-950/80 backdrop-blur">
        <ol className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-5 py-2">
          {STAGES.map((s, i) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => go(i)}
                aria-current={i === active ? 'step' : undefined}
                className={`whitespace-nowrap rounded-full px-3 py-1 text-sm transition-colors ${i === active ? 'bg-sky-700 font-semibold text-on-accent shadow-[0_0_18px_-2px_rgba(56,189,248,.8)]' : 'text-slate-300 hover:bg-white/10'}`}
              >
                {i + 1}. {s.short}
              </button>
            </li>
          ))}
        </ol>
        <div className="h-0.5 bg-white/5" aria-hidden>
          <motion.div
            data-testid="beam"
            className="h-full bg-gradient-to-r from-sky-400 to-emerald-400 shadow-[0_0_12px_rgba(56,189,248,.9)]"
            initial={false}
            animate={{ width: `${((active + 1) / STAGES.length) * 100}%` }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          />
        </div>
      </nav>

      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-10 px-5 lg:grid-cols-2">
        <div className="min-w-0">
          {STAGES.map((s, i) => (
            <section
              key={s.id}
              id={s.id}
              data-i={i}
              data-testid="stage"
              ref={(el) => {
                refs.current[i] = el
              }}
              className={`flex scroll-mt-28 flex-col justify-center py-12 transition-opacity duration-500 lg:min-h-[85vh] ${isDesktop && i !== active ? 'opacity-40' : 'opacity-100'}`}
            >
              <Reveal>
                <p className="font-mono text-sm text-glow">Step {i + 1} of {STAGES.length}</p>
                <h2 className="font-display mt-2 text-3xl font-bold tracking-tight">{s.title}</h2>
                <p className="mt-3 max-w-md text-slate-300">{s.text}</p>
              </Reveal>
              {!isDesktop && (
                <div className="mt-6">
                  <s.Visual active={active === i} />
                </div>
              )}
            </section>
          ))}
        </div>
        {isDesktop && (
          <div className="relative">
            <div className="sticky top-28 flex h-[calc(100vh-7rem)] items-center" data-testid="sticky-visual"><div className="w-full">
              <ActiveVisual key={STAGES[active].id} active /></div>
            </div>
          </div>
        )}
      </div>

      <section className="border-t border-white/10 bg-black/30 py-20">
        <div className="mx-auto max-w-6xl px-5">
          <h2 className="font-display max-w-3xl text-3xl font-extrabold sm:text-4xl">The LLM drafts. The engine verifies. You approve.</h2>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/studio" className="btn-primary btn-lg">
              Open Studio
            </Link>
            <Link to="/" className="btn-secondary btn-lg">
              Back to overview
            </Link>
          </div>
        </div>
      </section>
    </main>
  )
}
