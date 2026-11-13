// One simple line icon per Studio tool, drawn on the tool's glass card in the hub.
// Our own 24x24 SVG path data (no icon library). Stroked, never filled, so they read like the reference's line icons.

export const ICONS: Record<string, string> = {
  // build
  workbench: 'M8 6l-6 6 6 6M16 6l6 6-6 6',
  agent: 'M12 16V4M7 9l5-5 5 5M4 20h16',
  templates: 'M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5',
  // understand
  why: 'M12 21a9 9 0 1 0 0-18a9 9 0 1 0 0 18zM9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5v.5',
  map: 'M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18',
  gaps: 'M10.5 18a7.5 7.5 0 1 0 0-15a7.5 7.5 0 1 0 0 15zM16 16l5 5M8 10.5h5',
  // test
  evaluate: 'M3 6l1.5 1.5L7 5M3 12l1.5 1.5L7 11M3 18l1.5 1.5L7 17M10 6h11M10 12h11M10 18h11',
  redteam: 'M12 21a9 9 0 1 0 0-18a9 9 0 1 0 0 18zM12 16a4 4 0 1 0 0-8a4 4 0 1 0 0 8zM12 1v4M12 19v4M1 12h4M19 12h4',
  strength: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3zM9 12l2 2 4-4',
  replay: 'M3 12a9 9 0 1 0 3-6.7M3 4v5h5M12 7v5l3 2',
  // ship
  patch: 'M12 4v8M8 8h8M8 18h8M4 2h16v20H4z',
  sdk: 'M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0V8zM12 18v4',
  export: 'M3 7l9-4 9 4v10l-9 4-9-4V7zM3 7l9 4 9-4M12 11v10',
  // operate
  device: 'M3 11l9-8 9 8M5 9v12h14V9M10 21v-6h4v6',
  audit: 'M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1',
  history: 'M6 3v12M18 9a3 3 0 1 0 0-6a3 3 0 1 0 0 6zM6 21a3 3 0 1 0 0-6a3 3 0 1 0 0 6zM18 9a9 9 0 0 1-9 9',
  scorecard: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
}

/** The icon of a tool; a plain square if a new tool has none yet (a unit test makes sure that never ships). */
export function iconFor(toolId: string): string {
  return ICONS[toolId] ?? 'M4 4h16v16H4z'
}
