/** The one list of Studio tools. The hub page renders it; adding a tool means adding an entry here and a route in App.tsx.
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
    how: ['Upload a Python agent or MCP server.', 'Describe rules in English; a model drafts YOG.', 'The engine checks it and you approve it.'],
    limit: 'Your code is read, never run. A model drafts but never decides.',
  },
  {
    id: 'templates', name: 'Templates', group: 'build', status: 'next', to: '/studio/templates',
    purpose: 'Start from a ready-made safety pack.',
    how: ['Pick a pack, for example smart home or file access.', 'Read the English and the YOG side by side.', 'Load it into the rules page and edit.'],
    limit: 'Templates are starting points, not approved policies.',
  },
  {
    id: 'why', name: 'Why-Explainer', group: 'understand', status: 'next', to: '/studio/why',
    purpose: 'See the proof behind any ALLOW or DENY.',
    how: ['Pick a scenario or type one.', 'The engine decides and records every clause it tried.', 'You see which clause fired and why DENY beat ALLOW.'],
    limit: 'It explains decisions the engine made. It never makes its own.',
  },
  {
    id: 'gaps', name: 'Gap Analyzer', group: 'understand', status: 'next', to: '/studio/gaps',
    purpose: 'Find rules that never fire and tools with no rule.',
    how: ['Read the policy and the agent’s tool list.', 'Check for dead rules, shadowed allows and uncovered tools.', 'Get a coverage score with each finding linked to a line.'],
    limit: 'Static analysis only. It reports what it can prove, not what might happen.',
  },
  {
    id: 'evaluate', name: 'Scenario tests', group: 'test', status: 'ready', to: '/review',
    purpose: 'Run generated test cases through the engine.',
    how: ['Studio generates scenarios from your tools and policy.', 'Each one runs through the engine.', 'Green ALLOW and red DENY, with a reason and a trace.'],
    limit: 'It tests the policy, not the agent.',
  },
  {
    id: 'redteam', name: 'Red-Team', group: 'test', status: 'next', to: '/studio/red-team',
    purpose: 'Try to slip past your own policy.',
    how: ['Generate edge cases: boundary values, time edges, missing facts.', 'Run them through the engine.', 'See which ones were allowed that you would not expect.'],
    limit: 'It finds weak spots in rules. It does not attack a live system.',
  },
  {
    id: 'patch', name: 'Patch agent', group: 'ship', status: 'ready', to: '/modify',
    purpose: 'Get a minimal diff that adds the checks.',
    how: ['Studio finds each tool function.', 'It adds one guard line above each, plus one import.', 'You review the diff and download the patched file.'],
    limit: 'It never rewrites your file. Only the guard lines change.',
  },
  {
    id: 'export', name: 'Export Pack', group: 'ship', status: 'next', to: '/studio/export',
    purpose: 'Download everything in one zip.',
    how: ['Needs an approved policy.', 'Studio bundles the policy, readback, test report and patch.', 'You download one file to hand over.'],
    limit: 'The bundle never contains keys or other sessions’ data.',
  },
  {
    id: 'sdk', name: 'Runtime Guard', group: 'ship', status: 'next', to: '/studio/sdk',
    purpose: 'The small library the patched agent imports.',
    how: ['Copy the guard module next to your agent.', 'Each tool call asks the policy first.', 'Any error means DENY, never ALLOW.'],
    limit: 'It enforces the policy you approved. It does not write or change rules.',
  },
  {
    id: 'device', name: 'Device simulator', group: 'operate', status: 'ready', to: '/device',
    purpose: 'Watch YOG block a command on a simulated home.',
    how: ['Set the clock and the guard.', 'Send a command such as unlock the door.', 'See the decision, the reason and the device state.'],
    limit: 'Everything is simulated. No real device is controlled.',
  },
  {
    id: 'audit', name: 'Audit Log', group: 'operate', status: 'next', to: '/studio/audit',
    purpose: 'A record of every decision the guard made.',
    how: ['Each decision is stored with time, action and reason.', 'Filter and search the list.', 'Export it as CSV or replay a day.'],
    limit: 'The log is per visitor and bounded. It is not long-term storage.',
  },
  {
    id: 'history', name: 'Version History', group: 'operate', status: 'next', to: '/studio/history',
    purpose: 'Every approved version, with diffs and rollback.',
    how: ['Each approval is saved as a version.', 'Compare any two side by side.', 'Restore an old one; it still needs approving again.'],
    limit: 'Versions are never edited after they are saved.',
  },
]
