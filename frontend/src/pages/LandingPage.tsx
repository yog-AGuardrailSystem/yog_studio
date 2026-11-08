import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react'
import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { Section } from '../components/Section'
import { Term } from '../components/Term'
import { Counter } from '../components/motion/Counter'
import { LlmVsYog } from '../components/motion/LlmVsYog'
import { Marquee } from '../components/motion/Marquee'
import { Pipeline } from '../components/motion/Pipeline'
import { Reveal } from '../components/motion/Reveal'
import { Spotlight } from '../components/motion/Spotlight'
import { Gate } from '../components/three/Gate'

const ENGINE_REPO = 'https://github.com/yog-AGuardrailSystem/yog_engine'

const POLICY = `fact role(alice, resident)
fact night(now)

allow can_unlock(User, Door):
    role(User, resident)

deny can_unlock(User, Door):
    night(now)`

const STEPS = [
  ['Upload', 'Drop in a Python agent or MCP server.'],
  ['Find tools', 'Static analysis lists what it can do. Your code never runs.'],
  ['Write rules', 'Say what is allowed in plain English.'],
  ['Retrieve examples', 'Similar example policies are looked up for the model.'],
  ['Draft', 'An LLM drafts the YOG policy.'],
  ['Verify', 'The engine checks it. Errors go back to the model, up to 3 tries.'],
  ['Approve', 'You read it back in English and click Approve.'],
  ['Test', 'Generated scenarios run: green ALLOW, red DENY, with reasons.'],
  ['Patch', 'A minimal diff wraps tool calls in yog.check().'],
] as const

const PIPELINE = [
  { name: 'Source', sample: 'deny can_unlock(...)' },
  { name: 'Tokens', sample: 'DENY  IDENT  LPAREN …' },
  { name: 'AST', sample: 'Decision(deny, can_unlock)' },
  { name: 'Checks', sample: 'syntax, variables, no recursion' },
  { name: 'Decision', sample: 'DENY + reason + trace' },
] as const

const COMPONENTS = [
  ['1', 'Compiler and engine', 'A policy compiles; you see its tokens, tree and decisions.', 'Built by the engine team'],
  ['2', 'One custom app', 'Upload, rules, review, tests and patch happen in one place.', 'This app'],
  ['3', 'RAG + LLM translator', 'English rule in; retrieved examples and generated YOG out.', 'Rules page'],
  ['4', 'Agent evaluation', 'A table of scenarios with green ALLOW and red DENY, plus reasons.', 'Review page'],
  ['5', 'Script modifier', 'Side-by-side diff of your agent before and after yog.check().', 'Patch page'],
] as const

// real tool names from examples/agents/*
const TOOLS = ['unlock_door', 'lock_door', 'set_thermostat', 'open_valve', 'get_status', 'run_query', 'drop_table', 'backup_database', 'read_file', 'write_file', 'delete_file', 'ls_dir', 'transfer_funds', 'get_balance', 'send_receipt_email']

const WHY = [
  ['Deterministic', 'The same input gives the same decision, every run, with a reason.'],
  ['Human-approved', 'No policy goes live without a passing check, a readback and your approval.'],
  ['Your code never runs', 'Agents are read with static analysis. Only policies are evaluated.'],
  ['A small diff, not a rewrite', 'Studio shows exactly which lines change, and leaves the rest of your file alone.'],
] as const

const COUNTERS: [number, string][] = [
  [5, 'components you can see working'],
  [9, 'steps from upload to patch'],
  [3, 'tries for the draft to pass the engine'],
]

/** CSS-only stand-in when WebGL is unavailable (or ?fx=off). */
function HeroCard() {
  return (
    <div className="glass p-5" aria-label="Example decision">
      <p className="font-mono text-xs text-slate-400">agent → smart_home.unlock_door</p>
      <div className="relative mt-4 h-40">
        <div className="hero-state hero-allow absolute inset-0">
          <p className="font-mono text-sm text-slate-400">time: 14:00 · user: alice</p>
          <p className="mt-3 inline-block rounded-md border-2 border-emerald-400 px-3 py-1 font-display text-2xl font-extrabold text-emerald-300">ALLOW</p>
          <p className="mt-3 text-sm text-slate-300">alice is a resident. Door unlocks.</p>
        </div>
        <div className="hero-state hero-deny absolute inset-0">
          <p className="font-mono text-sm text-slate-400">time: 03:00 · user: alice</p>
          <p className="mt-3 inline-block rounded-md border-2 border-red-400 px-3 py-1 font-display text-2xl font-extrabold text-red-300">DENY</p>
          <p className="mt-3 text-sm text-slate-300">Rule: no unlocking at night. DENY beats ALLOW. Door stays locked.</p>
        </div>
      </div>
    </div>
  )
}

/** Vertical progress line that fills as the steps scroll past. */
function StepsTimeline() {
  const ref = useRef<HTMLOListElement>(null)
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 75%', 'end 60%'] })
  const scaleY = useTransform(scrollYProgress, [0, 1], [0, 1])
  return (
    <div className="relative">
      <div className="absolute bottom-2 left-3 top-2 w-px bg-slate-700 sm:left-4" aria-hidden />
      <motion.div
        className="absolute bottom-2 left-3 top-2 w-px origin-top bg-gradient-to-b from-sky-400 to-emerald-400 shadow-[0_0_10px_rgba(56,189,248,.8)] sm:left-4"
        style={{ scaleY: reduce ? 1 : scaleY }}
        data-testid="steps-line"
        aria-hidden
      />
      <ol ref={ref} className="space-y-3 pl-10 sm:pl-14">
        {STEPS.map(([name, text], i) => (
          <Reveal key={name} delay={0.03 * (i % 3)}>
            <li className="glass relative p-4" data-testid="step-card">
              <span
                className="absolute -left-[2.35rem] top-5 flex h-5 w-5 items-center justify-center rounded-full border border-sky-400 bg-slate-950 font-mono text-[10px] text-sky-300 sm:-left-[3.1rem]"
                aria-hidden
              >
                {i + 1}
              </span>
              <p className="font-display text-lg font-bold">{name}</p>
              <p className="mt-1 text-sm text-slate-300">{text}</p>
            </li>
          </Reveal>
        ))}
      </ol>
    </div>
  )
}

const HEAD = 'Let your AI agent act. Let rules decide what it may do.'.split(' ')

export default function LandingPage() {
  const reduce = useReducedMotion()
  const word = (t: string, i: number, cls = '') => (
    <motion.span
      key={i}
      className={`inline-block ${cls}`}
      initial={reduce ? false : { opacity: 0, y: 28, filter: 'blur(8px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      transition={{ duration: 0.6, delay: 0.08 * i, ease: 'easeOut' }}
    >
      {t}&nbsp;
    </motion.span>
  )

  return (
    <main>
      {/* 1. Hero: 3D */}
      <section className="flex min-h-[calc(100vh-3.5rem)] items-center py-10">
        <div className="mx-auto grid w-full max-w-6xl items-center gap-8 px-5 lg:grid-cols-[0.9fr_1.3fr]">
          <div>
            <motion.p
              className="mb-4 text-xs font-semibold uppercase tracking-widest text-glow"
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              Policy guardrails for AI agents
            </motion.p>
            <h1 className="font-display text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-6xl">
              {HEAD.map((w, i) => word(w, i, i >= 7 ? 'grad-text' : ''))}
            </h1>
            <Reveal delay={0.5}>
              <p className="mt-6 max-w-xl text-lg text-slate-300">
                YOG Studio turns plain-English rules into a checked policy that allows or blocks every action your agent tries, the same way every time.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/studio" className="btn-primary btn-lg">
                  Open Studio
                </Link>
                <Link to="/how-it-works" className="btn-secondary btn-lg">
                  See how it works
                </Link>
              </div>
              <p className="mt-5 text-sm text-slate-400">Try it: pick an action in the scene. YOG decides before it reaches the lock.</p>
            </Reveal>
          </div>
          <div className="relative h-[27rem] sm:h-[32rem]" data-testid="hero-visual">
            <Gate className="h-full w-full" fallback={<HeroCard />} />
          </div>
        </div>
      </section>

      {/* tool marquee */}
      <section className="border-y border-white/10 bg-black/20 py-5" aria-label="Tools YOG can guard">
        <Marquee items={TOOLS} />
      </section>

      {/* 2. Problem */}
      <Section
        eyebrow="The problem"
        title={
          <>
            Agents now take real actions. <span className="grad-text">Their guardrails are only probable.</span>
          </>
        }
      >
        <p className="mb-8 max-w-3xl text-lg text-slate-300">
          AI agents and MCP servers unlock doors, delete databases, move money and open valves. A prompt that says “never do this” is advice, and a clever message can talk the model out of it. For actions that matter you need an answer that is the same every time, with a reason you can read afterwards.
        </p>
        <LlmVsYog />
      </Section>

      {/* 3. What is YOG */}
      <Section id="what-is-yog" band eyebrow="What is YOG" title="A small language for rules. The same input always gives the same answer.">
        <div className="grid items-start gap-6 lg:grid-cols-2">
          <Reveal>
            <pre className="overflow-x-auto rounded-xl border border-white/10 bg-black/50 p-5 font-mono text-sm leading-relaxed text-sky-100">{POLICY}</pre>
          </Reveal>
          <Reveal delay={0.12}>
            <Spotlight className="p-5">
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
                In English <Term tip="Studio reads the policy back to you in plain English before you approve it.">(readback)</Term>
              </p>
              <ul className="mt-3 space-y-2 text-slate-200">
                <li>Residents may unlock the door.</li>
                <li>Nobody may unlock it at night.</li>
                <li>
                  If the two clash, <Term tip="Conflict rule: DENY beats ALLOW, and anything not allowed is denied by default.">DENY wins</Term>.
                </li>
              </ul>
              <p className="mt-4 text-sm text-slate-400">
                Rules are <Term tip="Facts are data the engine knows, like role(alice, resident).">facts</Term>, derived rules, and allow or deny decisions. Every answer comes with a reason and a trace.
              </p>
            </Spotlight>
          </Reveal>
        </div>
      </Section>

      {/* 4. How YOG is built */}
      <Section eyebrow="How YOG is built" title="A real compiler sits underneath.">
        <Pipeline steps={PIPELINE} />
        <Reveal>
          <p className="mt-8 max-w-3xl text-slate-300">
            The engine team built the language and the checker. A Python reference interpreter works today and Studio runs on it. A C compiler is in progress: the lexer is done and tested under ASan and UBSan.{' '}
            <a className="link" href={ENGINE_REPO} target="_blank" rel="noreferrer">
              yog_engine on GitHub
            </a>
          </p>
        </Reveal>
      </Section>

      {/* 5. What Studio does */}
      <Section band eyebrow="What Studio does" title="From an agent file to a tested policy, in nine steps.">
        <div className="max-w-2xl">
          <StepsTimeline />
        </div>
      </Section>

      {/* 6. Principle */}
      <section className="flex min-h-[60vh] items-center py-20">
        <div className="mx-auto w-full max-w-6xl px-5">
          <Reveal>
            <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-glow">The rule behind the tool</p>
            <h2 className="font-display max-w-4xl text-3xl font-extrabold leading-tight sm:text-6xl">
              The LLM <span className="grad-text">drafts.</span> The engine <span className="grad-text">verifies.</span> You <span className="grad-text">approve.</span>
            </h2>
            <p className="mt-6 max-w-2xl text-lg text-slate-300">
              A model may help write the policy. It never decides at runtime, and nothing goes live without a passing check, an English readback and your click. At runtime, YOG decides.
            </p>
          </Reveal>
          <div className="mt-10 grid gap-4 sm:grid-cols-3" data-testid="counters">
            {COUNTERS.map(([n, label]) => (
              <Spotlight key={label} className="p-5">
                <p className="font-display text-5xl font-extrabold text-glow">
                  <Counter to={n} />
                </p>
                <p className="mt-1 text-sm text-slate-300">{label}</p>
              </Spotlight>
            ))}
          </div>
        </div>
      </section>

      {/* 7. Components */}
      <Section band eyebrow="What you can see working" title="Five parts, each with a visible moment.">
        <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {COMPONENTS.map(([n, name, text, where]) => (
            <Spotlight key={n} as="li" className="p-5">
              <p className="font-mono text-xs text-slate-500">{n}</p>
              <p className="font-display text-lg font-bold">{name}</p>
              <p className="mt-1 text-sm text-slate-300">{text}</p>
              <p className="mt-3 text-xs font-semibold text-glow">{where}</p>
            </Spotlight>
          ))}
          <Spotlight as="li" className="p-5">
            <p className="font-mono text-xs text-glow">Demo</p>
            <p className="font-display text-lg font-bold">Simulated smart device</p>
            <p className="mt-1 text-sm text-slate-300">A lock, valve and thermostat run by an agent. Watch YOG block a dangerous command.</p>
            <Link to="/device" className="link mt-3 inline-block text-sm">
              Open the device
            </Link>
          </Spotlight>
        </ul>
      </Section>

      {/* 8. Why useful */}
      <Section eyebrow="Why it is useful" title="Safety you can check, explain and repeat.">
        <div className="grid gap-4 md:grid-cols-2">
          {WHY.map(([t, d], i) => (
            <Reveal key={t} delay={0.06 * i}>
              <Spotlight className="h-full p-5">
                <p className="font-display text-lg font-bold">{t}</p>
                <p className="mt-1 text-slate-300">{d}</p>
              </Spotlight>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* 9. Final CTA */}
      <section className="flex min-h-[50vh] items-center py-16">
        <div className="mx-auto w-full max-w-6xl px-5">
          <Reveal>
            <h2 className="font-display max-w-3xl text-3xl font-extrabold tracking-tight sm:text-6xl">
              Try it on a <span className="grad-text">sample agent.</span>
            </h2>
            <p className="mt-4 max-w-xl text-lg text-slate-300">Pick a sample MCP server in Studio and write your first rule in English.</p>
            <Link to="/studio" className="btn-primary btn-lg mt-8">
              Open Studio
            </Link>
          </Reveal>
        </div>
      </section>
    </main>
  )
}
