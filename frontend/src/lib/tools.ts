/** The one list of Studio tools. The hub page renders it, every tool page reads its "how it works" from it, and the
 *  How-it-works page lists it. Adding a tool means adding an entry here and a route in App.tsx.
 *  `status: 'ready'` tools open; `'next'` tools are listed honestly as not built yet and have no link. */
export type ToolGroup = 'build' | 'understand' | 'test' | 'ship' | 'operate'

export interface StudioTool {
  id: string
  name: string
  group: ToolGroup
  /** one line: what it is for */
  purpose: string
  /** three short steps: how it works */
  how: [string, string, string]
  /** what it deliberately does not do */
  limit: string
  to: string
  status: 'ready' | 'next'
}

export const GROUPS: { id: ToolGroup; title: string; blurb: string }[] = [
  { id: 'build', title: 'Build a policy', blurb: 'Turn what you want into YOG.' },
  { id: 'understand', title: 'Understand it', blurb: 'See why the engine decides what it decides.' },
  { id: 'test', title: 'Test it', blurb: 'Find out whether the policy holds up.' },
  { id: 'ship', title: 'Ship it', blurb: 'Take the policy into your agent.' },
  { id: 'operate', title: 'Operate it', blurb: 'Watch it work and keep a record.' },
]

export const TOOLS: StudioTool[] = [
  {
    id: 'workbench', name: 'Workbench', group: 'build', status: 'ready', to: '/studio/workbench',
    purpose: 'Write YOG with a live compiler beside you.',
    how: ['Type or paste YOG in the editor.', 'Tokens, AST and errors update as you type.', 'Add “# -> DENY” after a query to turn it into a test.'],
    limit: 'It runs the engine on the text you give it. It does not look at your agent.',
  },
  {
    id: 'agent', name: 'Agent tools', group: 'build', status: 'ready', to: '/agent',
    purpose: 'Upload an agent and get a policy for the tools it can call.',
    how: ['Upload a Python agent. MCP servers, OpenAI-style tool schemas, LangChain, OpenAI Agents SDK, CrewAI and PydanticAI are recognised.', 'Describe rules in English; a model drafts YOG.', 'The engine checks it and you approve it.'],
    limit: 'Your code is read, never run. A model drafts but never decides.',
  },
  {
    id: 'templates', name: 'Templates', group: 'build', status: 'ready', to: '/studio/templates',
    purpose: 'Start from a ready-made safety pack.',
    how: ['Pick one or more rules from a pack, for example smart home or file access.', 'The engine checks that the combination compiles.', 'Open it in the workbench and edit.'],
    limit: 'Templates are starting points, not approved policies. Drafted ones are marked until the team reviews them.',
  },
  {
    id: 'why', name: 'Why-Explainer', group: 'understand', status: 'ready', to: '/studio/why',
    purpose: 'See the proof behind any ALLOW or DENY.',
    how: ['Pick a request, or type one.', 'Every allow and deny rule for that action is replayed against it.', 'You see which rule fired, and where each other rule stopped.'],
    limit: 'It explains decisions the engine made. If it ever disagrees with the engine, it hides itself and shows the engine’s answer.',
  },
  {
    id: 'map', name: 'Policy Map', group: 'understand', status: 'ready', to: '/studio/map',
    purpose: 'See every decision at once, as a grid.',
    how: ['Choose an action and two inputs, such as hour and day.', 'The engine decides every combination.', 'Allowed and denied cells form shapes you can read; click one for its proof.'],
    limit: 'It shows what the policy does, not what it should do. Grids are capped at 2,000 cells.',
  },
  {
    id: 'gaps', name: 'Gap Analyzer', group: 'understand', status: 'ready', to: '/studio/gaps',
    purpose: 'Find rules that never fire and tools with no rule.',
    how: ['Read the policy and the agent’s tool list.', 'Check for dead rules, shadowed allows, duplicates and uncovered tools.', 'Each finding says whether it is proved or only a heuristic, with the lines involved.'],
    limit: 'Static analysis only. It reports what it can show, not what might happen at run time.',
  },
  {
    id: 'evaluate', name: 'Scenario tests', group: 'test', status: 'ready', to: '/review',
    purpose: 'Run generated test cases through the engine.',
    how: ['Studio generates scenarios from your tools and policy.', 'Each one runs through the engine.', 'Green ALLOW and red DENY, with a reason and a trace.'],
    limit: 'It tests the policy, not the agent.',
  },
  {
    id: 'redteam', name: 'Red-Team', group: 'test', status: 'ready', to: '/studio/red-team',
    purpose: 'Try to slip past your own policy.',
    how: ['State what must always hold, for example “never unlock between 23 and 5”.', 'Studio tries boundaries, missing facts, odd actors and extreme values.', 'Anything that breaks a stated rule is a counterexample.'],
    limit: 'It finds weak spots. Finding none does not prove the policy safe, and it never attacks a live system.',
  },
  {
    id: 'strength', name: 'Test Strength', group: 'test', status: 'ready', to: '/studio/strength',
    purpose: 'Check that your tests would notice a broken policy.',
    how: ['Studio makes small breaking edits to the policy: flip a comparison, shift a number, drop a rule.', 'It runs your scenarios against each edited copy.', 'An edit no scenario notices is a gap in your tests.'],
    limit: 'Some surviving edits change nothing in practice. The score is a guide, not a guarantee.',
  },
  {
    id: 'replay', name: 'Trace Replay', group: 'test', status: 'ready', to: '/studio/replay',
    purpose: 'Ask a policy what it would have said to past calls.',
    how: ['Paste a list of recorded tool calls, or use the audit log.', 'Each call is decided by the policy, and by a second policy if you pick one.', 'See what would have been blocked, and which calls change between versions.'],
    limit: 'It only reads data. No call in the list is ever executed.',
  },
  {
    id: 'patch', name: 'Patch agent', group: 'ship', status: 'ready', to: '/modify',
    purpose: 'Get a minimal diff that adds the checks.',
    how: ['Studio finds each tool function.', 'It adds one guard line above each, plus one import.', 'You review the diff and download the patched file.'],
    limit: 'It never rewrites your file. Only the guard lines change.',
  },
  {
    id: 'sdk', name: 'Runtime Guard', group: 'ship', status: 'ready', to: '/studio/sdk',
    purpose: 'The small library the patched agent imports.',
    how: ['Copy the guard module next to your agent.', 'Each tool call asks the policy first, one call at a time.', 'Any error means DENY, never ALLOW. A hash pin refuses a policy file that changed after approval.'],
    limit: 'It enforces the policy you approved. It does not write or change rules.',
  },
  {
    id: 'export', name: 'Export Pack', group: 'ship', status: 'ready', to: '/studio/export',
    purpose: 'Download everything in one checksummed zip.',
    how: ['Needs an approved policy.', 'Studio bundles the policy, a report, the test results and, if you add one, the patched agent.', 'A manifest lists the SHA-256 of every file.'],
    limit: 'The pack never contains keys or other visitors’ data, and the offline placeholder policy is refused.',
  },
  {
    id: 'device', name: 'Device simulator', group: 'operate', status: 'ready', to: '/device',
    purpose: 'Watch YOG block a command on a simulated home.',
    how: ['Set the clock and the guard.', 'Send a command such as unlock the door.', 'See the decision, the reason and the device state.'],
    limit: 'Everything is simulated. No real device is controlled.',
  },
  {
    id: 'audit', name: 'Audit Log', group: 'operate', status: 'ready', to: '/studio/audit',
    purpose: 'A tamper-evident record of every decision.',
    how: ['Each device decision is saved with its time, command, reason and policy.', 'Every entry carries the hash of the one before it; Verify rechecks the chain.', 'Filter, replay the day with the slider, or export CSV.'],
    limit: 'It is per visitor, bounded and expires. It detects edits; it is not long-term storage.',
  },
  {
    id: 'history', name: 'Version History', group: 'operate', status: 'ready', to: '/studio/history',
    purpose: 'Every approved version, with diffs and rollback.',
    how: ['Each approval is saved as a version and never edited.', 'Compare two: the text diff, plus which requests get a different answer.', 'Restore an old one; it is saved as a new version.'],
    limit: 'Impact is measured on generated probe requests, so it shows differences it found, not every difference.',
  },
  {
    id: 'scorecard', name: 'Scorecard', group: 'operate', status: 'ready', to: '/studio/scorecard',
    purpose: 'A few honest numbers about one policy.',
    how: ['Studio runs the checks above on your policy.', 'Tools covered, rules exercised, proved problems, suspicious ALLOWs, test strength.', 'Each number links to its tool; a check not run says so.'],
    limit: 'A good score is not a proof of safety. Numbers not measured are shown as not measured.',
  },
]
