import { Link } from 'react-router-dom'
import { Section } from '../components/Section'
import { Term } from '../components/Term'

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
  ['Source', 'deny can_unlock(...)'],
  ['Tokens', 'DENY  IDENT  LPAREN …'],
  ['AST', 'Decision(deny, can_unlock)'],
  ['Checks', 'syntax, variables, no recursion'],
  ['Decision', 'DENY + reason + trace'],
] as const

const COMPONENTS = [
  ['1', 'Compiler and engine', 'A policy compiles; you see its tokens, tree and decisions.', 'Built by the engine team'],
  ['2', 'One custom app', 'Upload, rules, review, tests and patch happen in one place.', 'This app'],
  ['3', 'RAG + LLM translator', 'English rule in; retrieved examples and generated YOG out.', 'Rules page'],
  ['4', 'Agent evaluation', 'A table of scenarios with green ALLOW and red DENY, plus reasons.', 'Review page'],
  ['5', 'Script modifier', 'Side-by-side diff of your agent before and after yog.check().', 'Patch page'],
] as const

function HeroCard() {
  return (
    <div className="hero-card relative rounded-2xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-900/5" aria-label="Example decision">
      <p className="font-mono text-xs text-slate-500">agent → smart_home.unlock_door</p>
      <div className="relative mt-4 h-40">
        <div className="hero-state hero-allow absolute inset-0">
          <p className="font-mono text-sm text-slate-500">time: 14:00 · user: alice</p>
          <p className="mt-3 inline-block rounded-md bg-emerald-100 px-3 py-1 font-display text-2xl font-extrabold text-emerald-800">ALLOW</p>
          <p className="mt-3 text-sm text-slate-600">alice is a resident. Door unlocks.</p>
        </div>
        <div className="hero-state hero-deny absolute inset-0">
          <p className="font-mono text-sm text-slate-500">time: 03:00 · user: alice</p>
          <p className="mt-3 inline-block rounded-md bg-red-100 px-3 py-1 font-display text-2xl font-extrabold text-red-800">DENY</p>
          <p className="mt-3 text-sm text-slate-600">Rule: no unlocking at night. DENY beats ALLOW. Door stays locked.</p>
        </div>
      </div>
    </div>
  )
}

export default function LandingPage() {
  return (
    <main>
      {/* 1. Hero */}
      <section className="flex min-h-[calc(100vh-3.5rem)] items-center py-12">
        <div className="mx-auto grid w-full max-w-6xl items-center gap-12 px-5 lg:grid-cols-2">
          <div>
            <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-brand">Policy guardrails for AI agents</p>
            <h1 className="font-display text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-6xl">
              Let your AI agent act. Let rules decide what it may do.
            </h1>
            <p className="mt-6 max-w-xl text-lg text-slate-600">
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
          </div>
          <HeroCard />
        </div>
      </section>

      {/* 2. Problem */}
      <Section eyebrow="The problem" title="Agents now take real actions. Their guardrails are only probable." tone="muted">
        <div className="grid gap-8 md:grid-cols-2">
          <p className="text-lg text-slate-700">
            AI agents and MCP servers unlock doors, delete databases, move money and open valves. A prompt that says “never do this” is advice, and a clever message can talk the model out of it.
          </p>
          <p className="text-lg text-slate-700">
            For actions that matter you need an answer that is the same every time, with a reason you can read afterwards. That is what YOG gives you.
          </p>
        </div>
      </Section>

      {/* 3. What is YOG */}
      <Section
        id="what-is-yog"
        eyebrow="What is YOG"
        title="A small language for rules. The same input always gives the same answer."
      >
        <div className="grid items-start gap-6 lg:grid-cols-2">
          <pre className="overflow-x-auto rounded-xl bg-slate-950 p-5 font-mono text-sm leading-relaxed text-slate-100">{POLICY}</pre>
          <div className="rounded-xl border border-slate-200 p-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
              In English <Term tip="Studio reads the policy back to you in plain English before you approve it.">(readback)</Term>
            </p>
            <ul className="mt-3 space-y-2 text-slate-700">
              <li>Residents may unlock the door.</li>
              <li>Nobody may unlock it at night.</li>
              <li>
                If the two clash, <Term tip="Conflict rule: DENY beats ALLOW, and anything not allowed is denied by default.">DENY wins</Term>.
              </li>
            </ul>
            <p className="mt-4 text-sm text-slate-500">
              Rules are <Term tip="Facts are data the engine knows, like role(alice, resident).">facts</Term>, derived rules, and allow or deny decisions. Every answer comes with a reason and a trace.
            </p>
          </div>
        </div>
      </Section>

      {/* 4. How YOG is built */}
      <Section eyebrow="How YOG is built" title="A real compiler sits underneath." tone="muted">
        <ol className="grid gap-3 md:grid-cols-5">
          {PIPELINE.map(([name, sample], i) => (
            <li key={name} className="relative rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold text-brand">{i + 1}</p>
              <p className="font-display text-lg font-bold">{name}</p>
              <p className="mt-2 font-mono text-xs text-slate-500">{sample}</p>
            </li>
          ))}
        </ol>
        <p className="mt-6 max-w-3xl text-slate-700">
          The engine team built the language and the checker. A Python reference interpreter works today and Studio runs on it. A C compiler is in progress: the lexer is done and tested under ASan and UBSan.{' '}
          <a className="link" href={ENGINE_REPO} target="_blank" rel="noreferrer">
            yog_engine on GitHub
          </a>
        </p>
      </Section>

      {/* 5. What Studio does */}
      <Section eyebrow="What Studio does" title="From an agent file to a tested policy, in nine steps.">
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map(([name, text], i) => (
            <li key={name} className="rounded-xl border border-slate-200 p-4">
              <p className="font-mono text-xs text-slate-400">{String(i + 1).padStart(2, '0')}</p>
              <p className="font-display text-lg font-bold">{name}</p>
              <p className="mt-1 text-sm text-slate-600">{text}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* 6. Principle */}
      <section className="flex min-h-[60vh] items-center bg-slate-950 py-16 text-white">
        <div className="mx-auto w-full max-w-6xl px-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-sky-300">The rule behind the tool</p>
          <h2 className="font-display max-w-4xl text-3xl font-extrabold leading-tight sm:text-5xl">
            The LLM drafts. The engine verifies. You approve.
          </h2>
          <p className="mt-6 max-w-2xl text-lg text-slate-300">
            A model may help write the policy. It never decides at runtime, and nothing goes live without a passing check, an English readback and your click. At runtime, YOG decides.
          </p>
        </div>
      </section>

      {/* 7. Components */}
      <Section eyebrow="What you can see working" title="Five parts, each with a visible moment.">
        <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {COMPONENTS.map(([n, name, text, where]) => (
            <li key={n} className="rounded-xl border border-slate-200 p-5">
              <p className="font-mono text-xs text-slate-400">{n}</p>
              <p className="font-display text-lg font-bold">{name}</p>
              <p className="mt-1 text-sm text-slate-600">{text}</p>
              <p className="mt-3 text-xs font-semibold text-brand">{where}</p>
            </li>
          ))}
          <li className="rounded-xl border border-brand bg-sky-50 p-5">
            <p className="font-mono text-xs text-brand">Demo</p>
            <p className="font-display text-lg font-bold">Simulated smart device</p>
            <p className="mt-1 text-sm text-slate-600">A lock, valve and thermostat run by an agent. Watch YOG block a dangerous command.</p>
            <Link to="/device" className="link mt-3 inline-block text-sm">
              Open the device
            </Link>
          </li>
        </ul>
      </Section>

      {/* 8. Why useful */}
      <Section eyebrow="Why it is useful" title="Safety you can check, explain and repeat." tone="muted">
        <div className="grid gap-4 md:grid-cols-2">
          {[
            ['Deterministic', 'The same input gives the same decision, every run, with a reason.'],
            ['Human-approved', 'No policy goes live without a passing check, a readback and your approval.'],
            ['Your code never runs', 'Agents are read with static analysis. Only policies are evaluated.'],
            ['A small diff, not a rewrite', 'Studio shows exactly which lines change, and leaves the rest of your file alone.'],
          ].map(([t, d]) => (
            <div key={t} className="rounded-xl border border-slate-200 bg-white p-5">
              <p className="font-display text-lg font-bold">{t}</p>
              <p className="mt-1 text-slate-600">{d}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* 9. Final CTA */}
      <section className="flex min-h-[50vh] items-center py-16">
        <div className="mx-auto w-full max-w-6xl px-5">
          <h2 className="font-display max-w-3xl text-3xl font-extrabold tracking-tight sm:text-5xl">Try it on a sample agent.</h2>
          <p className="mt-4 max-w-xl text-lg text-slate-600">Pick a sample MCP server in Studio and write your first rule in English.</p>
          <Link to="/studio" className="btn-primary btn-lg mt-8">
            Open Studio
          </Link>
        </div>
      </section>
    </main>
  )
}
