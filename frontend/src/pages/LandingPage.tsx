import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { teamExamples, type TeamGroup } from '../api/compile'
import { CompilerExplorer, EXPLORER_LOAD_EVENT } from '../components/CompilerExplorer'
import { Section } from '../components/Section'
import { useAiMode } from '../lib/aiMode'
import { Term } from '../components/Term'
import { LlmVsYog } from '../components/motion/LlmVsYog'
import { CardFlow } from '../components/fx/CardFlow'
import { ClickRipple, CursorGlow, KeywordMarquee, Magnetic, Parallax, ParticleField, ScrollRail, SectionDots } from '../components/fx/Ambient'
import { PipelineFlow } from '../components/fx/PipelineFlow'
import { CompilerScenes } from '../components/scenes/CompilerScenes'
import { Reveal } from '../components/motion/Reveal'
import { Spotlight } from '../components/motion/Spotlight'
import { Gate } from '../components/three/Gate'
import { HeroGlobeView } from '../components/three/HeroGlobeView'
import { WhenNear } from '../components/three/WhenNear'

const ENGINE_REPO = 'https://github.com/yog-AGuardrailSystem/yog_engine'

// Each stage is what engine/c_front really does (docs/COMPILER.md, src/*): the IR is a clause table (no bytecode), and
// deny > allow > default deny is applied by the engine's check() layer on top of the VM's backtracking search.
const PIPELINE = [
  { name: 'Source', sample: 'deny can_access(U, D):' },
  { name: 'Lexer', sample: 'DENY IDENT LPAREN VAR …' },
  { name: 'Parser', sample: 'statements: a head and its body goals' },
  { name: 'Semantic analysis', sample: 'one role per name, ground facts, bound variables, no cycles' },
  { name: 'IR', sample: 'clause table and constant pool (no bytecode)' },
  { name: 'VM', sample: 'backtracking search, step and depth limits' },
  { name: 'Authorization', sample: 'deny > allow > default deny' },
  { name: 'C API', sample: 'yog_compile · yog_check' },
  { name: 'Studio', sample: 'yogc batch → ALLOW / DENY' },
] as const

// Measured by running the engine repo's own C test programs (scripts/c_engine_report.py reproduces these numbers).
// MEASURED_AT must equal the commit in engine/c_front/VERSION: backend/tests/test_engine_conformance.py enforces it,
// so re-vendoring the engine forces a re-measurement before the page can claim these figures again.
const MEASURED_AT = '200e481'
const COMPILER_FACTS: [string, string][] = [
  ['66', 'tests across the lexer, parser, semantic analyser, IR, VM and C API: all pass'],
  ['30,886', 'checks inside them, built with every warning an error and run under AddressSanitizer and UBSan'],
  ['25 / 25', 'queries of the team’s example file answer identically in the C compiler and the Python reference'],
]

// Quoted from the engine team's own lexer test report (see the section's source link). Scoped to the lexer.
const LEXER_FACTS: [string, string][] = [
  ['100%', 'line coverage of the lexer'],
  ['22 / 22', 'deliberately injected bugs (mutants) caught'],
  ['6,023', 'differential comparisons against the Python reference'],
  ['0', 'mismatches in those comparisons'],
]

// Measured by Studio on every commit: backend/tests/test_engine_conformance.py runs these through both engines and
// fails if the counts below stop matching the corpus.
const CROSS_ENGINE_FACTS: [string, string][] = [
  ['298 / 298', 'gold scenarios get the same decision and the same reason from the C engine and the Python reference'],
  ['95', 'gold policies compiled by both engines'],
]

const FALLBACK_GROUPS: Pick<TeamGroup, 'id' | 'title' | 'english' | 'graph'>[] = [
  { id: 'A', title: 'delete from a database', english: 'Only admins may delete from a database.' },
  { id: 'D', title: 'production deletes', english: 'Deleting in production needs all three conditions.' },
  { id: 'I', title: 'transfer limits', english: 'Customers may transfer only up to their own limit.' },
  { id: 'R', title: 'override pattern', english: 'Employees may access documents, except confidential ones.' },
]

const HEAD = 'A policy language with a compiler you can trust.'.split(' ')

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

export default function LandingPage() {
  const reduce = useReducedMotion()
  const { info } = useAiMode()
  const engineCaption = info?.engine === 'c'
    ? 'Tokens and the tree come from the reference parser; the checks and decisions come from the C compiler, as you type.'
    : 'Every token, check and decision above is produced by the Python reference engine as you type.'
  const [groups, setGroups] = useState<Pick<TeamGroup, 'id' | 'title' | 'english' | 'graph'>[]>(FALLBACK_GROUPS)
  const [sources, setSources] = useState<Record<string, string>>({})
  useEffect(() => {
    teamExamples().then((g) => { setGroups(g); setSources(Object.fromEntries(g.map((x) => [x.id, x.source]))) }).catch(() => undefined)
  }, [])

  function tryInExplorer(id: string) {
    const src = sources[id]
    if (!src) return
    window.dispatchEvent(new CustomEvent(EXPLORER_LOAD_EVENT, { detail: src }))
    document.getElementById('explorer')?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' })
  }

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
      <ScrollRail /><SectionDots /><ParticleField /><CursorGlow /><ClickRipple />
      {/* 1. Hero */}
      <section data-section="hero" id="hero" className="py-10 sm:py-14 lg:py-16">
        <div className="mx-auto grid w-full max-w-6xl items-center gap-6 px-5 lg:grid-cols-[1.05fr_0.95fr] lg:gap-4">
          <div>
            <motion.p className="mb-4 text-xs font-semibold uppercase tracking-widest text-glow" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }}>
              YOG · deterministic policy for AI agents
            </motion.p>
            <Parallax id="hero-title" speed={0.05}><h1 className="font-display max-w-4xl text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-6xl lg:text-5xl xl:text-6xl">
              {HEAD.map((w, i) => word(w, i, i >= 5 ? 'grad-text' : ''))}
            </h1></Parallax>
            <Reveal delay={0.4}>
              <p className="mt-6 max-w-xl text-lg text-slate-300">
                Write a rule once. YOG compiles it, checks it, and answers ALLOW or DENY for every action, the same way every time, with the reason attached.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Magnetic id="try"><a href="#explorer" className="btn-primary btn-lg">Try the compiler</a></Magnetic>
                <Magnetic id="workbench"><Link to="/studio/workbench" className="btn-secondary btn-lg">Open the workbench</Link></Magnetic>
              </div>
            </Reveal>
          </div>
          <HeroGlobeView className="h-[24rem] sm:h-[30rem] lg:h-[38rem]" />
        </div>
      </section>

      {/* 2. Live compiler explorer */}
      <section id="explorer" data-section="explorer" data-label="Try the compiler" className="pb-16 sm:pb-24" aria-label="Compiler explorer">
        <div className="mx-auto w-full max-w-6xl px-5">
          <Reveal>
            <CompilerExplorer />
            <p className="mt-3 text-sm text-slate-400">
              Edit the program. {engineCaption} Pick a group to load one of the team’s example policies.
            </p>
          </Reveal>
        </div>
      </section>

      {/* 2b. Stage by stage */}
      <Section eyebrow="Inside the compiler" title="Watch one program move through the stages.">
        <CompilerScenes />
      </Section>

      {/* 3. Why a compiler */}
      <Section
        band
        eyebrow="Why a compiler"
        title={<>Agents take real actions. <span className="grad-text">A prompt is only advice.</span></>}
      >
        <p className="mb-8 max-w-3xl text-lg text-slate-300">
          A prompt that says “never do this” can be talked around. A YOG policy is compiled and checked before anything runs, so the answer to “may the agent do this?” is a fact with a reason, not a probability.
        </p>
        <LlmVsYog />
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {[
            ['Deterministic', 'The same input gives the same decision on every run.'],
            ['DENY beats ALLOW', 'If two rules clash, the forbidding one wins. Anything not allowed is denied.'],
            ['Explainable', 'Every decision carries its reason: the clause that matched (or the default deny) and a trace of the facts it checked.'],
          ].map(([t, d]) => (
            <Spotlight key={t} className="p-5"><p className="font-display text-lg font-bold">{t}</p><p className="mt-1 text-slate-300">{d}</p></Spotlight>
          ))}
        </div>
      </Section>

      {/* 4. The language in a minute */}
      <Section eyebrow="The language in a minute" title="Facts, rules, and decisions.">
        <p className="mb-6 max-w-3xl text-slate-300">
          Six keywords carry the language: <Term tip="Ground data: fact role(alice, admin)">fact</Term>, <Term tip="A derived predicate built from others. Recursion is not allowed.">rule</Term>, <Term tip="Permits an action when the body holds.">allow</Term> and <Term tip="Forbids an action. DENY beats ALLOW.">deny</Term> define a policy, <code>query</code> asks a question, and <Term tip="Negates one condition inside a body: not role(User, banned)">not</Term> negates a condition. Each example below runs in the explorer.
        </p>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="example-cards">
          {groups.map((g) => (
            <Spotlight key={g.id} as="li" className="p-4">
              <p className="font-mono text-xs text-glow">Group {g.id}</p>
              <p className="font-display text-base font-bold">{g.title}</p>
              <p className="mt-1 text-sm text-slate-300">{g.english}</p>
              <CardFlow id={g.id} graph={g.graph} />
              <button type="button" className="link mt-3 text-sm" disabled={!sources[g.id]} onClick={() => tryInExplorer(g.id)} data-testid={`card-${g.id.replace('/', '')}`}>
                Run it in the explorer
              </button>
            </Spotlight>
          ))}
        </ul>
      </Section>

      {/* 5. Pipeline */}
      <Section band eyebrow="The pipeline" title="From source text to a decision, one stage at a time.">
        <PipelineFlow steps={PIPELINE} />
        <div className="mt-6"><KeywordMarquee /></div>
        <Reveal>
          <p className="mt-8 max-w-3xl text-slate-300">
            A Python reference interpreter defines the behaviour. The C compiler is the production implementation: a written contract freezes what both must agree on, and the engine team tests the C compiler with its own semantic tests and with differential tests against the reference.{' '}
            <a className="link" href={ENGINE_REPO} target="_blank" rel="noreferrer">yog_engine on GitHub</a>
          </p>
        </Reveal>
      </Section>

      {/* 6. Trust */}
      <Section eyebrow="A compiler you can trust" title="Checked against a reference, with the numbers.">
        <h3 className="mb-3 font-display text-lg font-bold">The C compiler, on the engine team’s own tests</h3>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="compiler-facts">
          {COMPILER_FACTS.map(([n, label]) => (
            <Spotlight key={label} as="li" className="p-5">
              <p className="font-display text-4xl font-extrabold text-glow">{n}</p>
              <p className="mt-1 text-sm text-slate-300">{label}</p>
            </Spotlight>
          ))}
        </ul>
        <p className="mt-3 max-w-3xl text-sm text-slate-400">
          Measured by running the test programs in{' '}
          <a className="link" href={ENGINE_REPO} target="_blank" rel="noreferrer">the engine repository</a> at commit {MEASURED_AT}.
        </p>
        <h3 className="mb-3 mt-8 font-display text-lg font-bold">The lexer, from the engine team’s test report</h3>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="lexer-facts">
          {LEXER_FACTS.map(([n, label]) => (
            <Spotlight key={label} as="li" className="p-5">
              <p className="font-display text-4xl font-extrabold text-glow">{n}</p>
              <p className="mt-1 text-sm text-slate-300">{label}</p>
            </Spotlight>
          ))}
        </ul>
        <p className="mt-3 max-w-3xl text-sm text-slate-400">
          Quoted from the lexer report in the engine repository; they describe the lexer only. In the explorer you can compare any program against the real C lexer, and see the clause table the C compiler builds, yourself.
        </p>
        <h3 className="mb-3 mt-8 font-display text-lg font-bold">Both engines, on Studio’s gold policies</h3>
        <ul className="grid gap-4 sm:grid-cols-2" data-testid="cross-engine-facts">
          {CROSS_ENGINE_FACTS.map(([n, label]) => (
            <Spotlight key={label} as="li" className="p-5">
              <p className="font-display text-4xl font-extrabold text-glow">{n}</p>
              <p className="mt-1 text-sm text-slate-300">{label}</p>
            </Spotlight>
          ))}
        </ul>
        <p className="mt-3 max-w-3xl text-sm text-slate-400">
          Measured by Studio itself: every gold scenario is run through both engines on each change, and Studio’s production build uses the C engine.
        </p>
      </Section>

      {/* 7. Explainable decisions + 3D gate */}
      <Section band eyebrow="Explainable decisions" title="Watch a rule decide.">
        <div className="grid items-center gap-8 lg:grid-cols-[0.9fr_1.3fr]">
          <div>
            <p className="text-lg text-slate-300">
              Pick an action. The scene applies the same rules as the policy: an allow for residents, a deny at night, and DENY wins. This is an in-browser demonstration of those rules; the explorer above runs the real engine.
            </p>
          </div>
          <div className="relative h-[26rem] sm:h-[30rem]" data-testid="hero-visual">
            <WhenNear className="h-full w-full"><Gate className="h-full w-full" fallback={<HeroCard />} /></WhenNear>
          </div>
        </div>
      </Section>

      {/* 8. Studio */}
      <Section eyebrow="Write YOG faster" title="Studio is the workbench around the compiler.">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[
            ['An editor that knows YOG', 'Colours, completion, live error markers, and one-click fixes for common mistakes.'],
            ['Tests inside the language', 'Add “# -> DENY” after a query. Click any result to see the exact clause that decided it.'],
            ['Describe a rule in English', 'Similar examples are retrieved, a model drafts YOG, the compiler checks it, and you approve it.'],
            ['Plain-English readback', 'Every policy is read back from its parsed form, never from a model.'],
            ['Agent tools', 'Upload a Python agent or MCP server, find its tools, and get a minimal diff that adds the checks.'],
            ['A device to try it on', 'A simulated lock, valve and thermostat show a dangerous command being blocked.'],
          ].map(([t, d]) => (
            <Spotlight key={t} className="p-5"><p className="font-display text-lg font-bold">{t}</p><p className="mt-1 text-slate-300">{d}</p></Spotlight>
          ))}
        </div>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link to="/studio" className="btn-primary btn-lg">Browse all tools</Link>
          <Link to="/studio/workbench" className="btn-secondary btn-lg">Open the workbench</Link>
          <Link to="/how-it-works" className="btn-secondary btn-lg">How Studio works</Link>
        </div>
      </Section>
    </main>
  )
}
