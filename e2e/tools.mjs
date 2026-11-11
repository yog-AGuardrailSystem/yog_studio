// Every Studio tool page, driven like a person would. Needs the frontend (5173) and the backend (8000, offline LLM is fine).
import path from 'node:path'
import { BASE, check, launch, overflowX, summary } from './lib.mjs'

const AXE = path.resolve('node_modules/axe-core/axe.min.js')
const RULES = ['color-contrast', 'button-name', 'link-name', 'label', 'image-alt', 'aria-valid-attr', 'aria-valid-attr-value', 'aria-required-attr', 'select-name']
const DEMO = (await import('node:fs')).readFileSync(new URL('../examples/policies/demo_smart_home.yog', import.meta.url), 'utf8')

const b = await launch()
const errors = []
const ctx = await b.newContext({ viewport: { width: 1360, height: 900 }, acceptDownloads: true })
const page = await ctx.newPage()
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()) })
page.on('dialog', (d) => d.accept())

const api = (p, body) => page.request.post(BASE + '/api' + p, { data: body })
const open = async (p, sel) => { await page.goto(BASE + p); await page.waitForSelector(sel, { timeout: 20000 }) }
async function axe(name) {
  if (process.env.NO_AXE) return                     // a production build's CSP blocks injected scripts, so axe only runs against the dev server
  await page.addScriptTag({ path: AXE }).catch(() => {})
  const r = await page.evaluate(async (rules) => await window.axe.run(document, { runOnly: { type: 'rule', values: rules } }), RULES)
  const v = r.violations.flatMap((x) => x.nodes.map((n) => `${x.id} ${n.target.join(' ').slice(0, 70)} | ${(n.any[0]?.message || '').slice(0, 80)}`))
  check(`axe: ${name}`, v.length === 0, '\n   ' + v.slice(0, 4).join('\n   '))
}
const text = (sel) => page.locator(sel).first().innerText()

// ---------------------------------------------------------------- why
await open('/studio/why', '[data-testid=tool-page-why]')
await page.waitForFunction(() => document.querySelectorAll('[data-testid=why-action] option').length > 3)
check('why: policy picker defaults to the demo (nothing approved yet)', (await text('[data-testid=policy-picker]')).includes('Demo policy'))
await page.selectOption('[data-testid=why-action]', 'can_unlock_door')
await page.fill('[data-testid=why-context]', 'hour(now, 3)')
await page.click('[data-testid=why-run]')
await page.waitForSelector('[data-testid=why-result]')
check('why: 3am unlock is DENY with the deny rule named', /DENY: the deny rule at line 24/.test(await text('[data-testid=why-verdict]')))
check('why: the matched deny clause is marked and its steps are listed', (await page.getAttribute('[data-testid=clause-24]', 'data-status')) === 'matched' && (await page.locator('[data-testid=why-clauses] li').count()) > 0)
check('why: the matching lines are highlighted in the listing', (await page.locator('[data-testid=line-marked]').count()) >= 2)
await page.fill('[data-testid=why-context]', 'hour(now, 14)')
await page.click('[data-testid=why-run]')
await page.waitForFunction(() => /^ALLOW/.test(document.querySelector('[data-testid=why-verdict]')?.textContent ?? ''))
check('why: 2pm unlock is ALLOW', true)
await page.fill('[data-testid=why-context]', 'garbage')
await page.click('[data-testid=why-run]')
await page.waitForSelector('[data-testid=tool-error]')
check('why: a bad fact shows an error, not a crash', true)
await page.click('[data-testid=how-toggle]')
check('why: how-it-works panel opens', (await page.locator('[data-testid=how-body]').count()) === 1)
await page.fill('[data-testid=why-context]', 'hour(now, 3)'); await page.click('[data-testid=why-run]'); await page.waitForSelector('[data-testid=why-result]')
await axe('why')

// ---------------------------------------------------------------- map -> why
await open('/studio/map', '[data-testid=tool-page-map]')
await page.waitForFunction(() => document.querySelectorAll('[data-testid=map-action] option').length > 3)
await page.selectOption('[data-testid=map-action]', 'can_unlock_door')
await page.selectOption('[data-testid=map-x]', 'hour'); await page.selectOption('[data-testid=map-y]', 'day')
await page.click('[data-testid=map-run]')
await page.waitForSelector('[data-testid=map-result]')
check('map: 7 days x 24 hours = 168 cells', (await page.locator('[data-cell]').count()) === 168)
check('map: 119 allowed, 49 denied', /119.*allowed.*49.*denied/s.test(await text('[data-testid=map-summary]')))
check('map: the night band is denied (03:00 cell)', (await page.locator('tbody tr').first().locator('[data-cell]').nth(3).getAttribute('data-cell')) === 'D')
await page.locator('tbody tr').first().locator('[data-cell]').nth(3).click()
await page.waitForSelector('[data-testid=why-result]')
check('map: clicking a cell opens the proof for that exact request', page.url().includes('/studio/why') && /DENY/.test(await text('[data-testid=why-verdict]')))
await open('/studio/map', '[data-testid=tool-page-map]')
await page.waitForFunction(() => document.querySelectorAll('[data-testid=map-action] option').length > 3)
await page.click('[data-testid=map-run]'); await page.waitForSelector('[data-testid=map-result]')
await axe('map')

// ---------------------------------------------------------------- gaps
await open('/studio/gaps', '[data-testid=tool-page-gaps]')
await page.waitForSelector('[data-testid=gaps-result]')
check('gaps: two rings and a findings list', (await page.locator('[data-testid=coverage-ring]').count()) === 2)
check('gaps: demo policy has 0 proved problems', (await text('[data-testid=gaps-proved]')) === '0')
await page.fill('[data-testid=gaps-tools]', 'unlock_door, lock_door, set_thermostat, open_valve, get_status, delete_all')
await page.click('[data-testid=gaps-run]')
await page.waitForFunction(() => document.querySelector('[data-finding=uncovered_tool]'))
check('gaps: a tool with no rule is found', /delete_all/.test(await text('[data-finding=uncovered_tool]')))
await axe('gaps')

// ---------------------------------------------------------------- red-team
await open('/studio/red-team', '[data-testid=tool-page-redteam]')
await page.waitForFunction(() => !document.querySelector('[data-testid=add-invariant]')?.disabled)
await page.click('[data-testid=add-invariant]')
await page.selectOption('[data-testid=invariant] select[aria-label=Action]', 'can_unlock_door')
await page.click('[data-testid=redteam-run]')
await page.waitForSelector('[data-testid=redteam-result]')
check('red-team: the night promise holds on the demo policy', (await text('[data-testid=rt-cx]')) === '0')
check('red-team: suspicious ALLOWs are listed', Number(await text('[data-testid=rt-sus]')) > 0)
await page.fill('[data-testid=invariant] input[aria-label="Hour from"]', '6'); await page.fill('[data-testid=invariant] input[aria-label="Hour to"]', '10')
await page.selectOption('[data-testid=invariant] select[aria-label="Must be"]', 'DENY')
await page.click('[data-testid=redteam-run]')
await page.waitForFunction(() => Number(document.querySelector('[data-testid=rt-cx]')?.textContent) > 0)
check('red-team: a false promise (DENY at 6-10) is caught with counterexamples', true)
await page.locator('[data-testid=rt-attacks] button', { hasText: 'Keep as a test' }).first().click()
check('red-team: a counterexample can be kept as a saved test', (await page.evaluate(() => JSON.parse(localStorage.getItem('yog.myScenarios') || '[]').length)) === 1)
await axe('red-team')

// ---------------------------------------------------------------- strength
await open('/studio/strength', '[data-testid=tool-page-strength]')
check('strength: shows the saved scenario', (await page.locator('[data-testid=mine-list] li').count()) === 1)
await page.click('[data-testid=strength-run]')
await page.waitForSelector('[data-testid=strength-result]')
check('strength: a score and survivors are shown (one test leaves most edits unnoticed)', /\d+%/.test(await text('[data-testid=strength-score]')) && Number(await text('[data-testid=strength-survived]')) > 3)
await axe('strength')

// ---------------------------------------------------------------- templates
await open('/studio/templates', '[data-testid=tpl-list]')
await page.waitForFunction(() => document.querySelectorAll('[data-testid=tpl-list] li').length >= 60)
await page.fill('[data-testid=tpl-search]', 'night')
check('templates: search narrows the list', (await page.locator('[data-testid=tpl-list] li').count()) < 60 && (await page.locator('[data-testid=tpl-list] li').count()) > 0)
await page.fill('[data-testid=tpl-search]', '')
await page.selectOption('[data-testid=tpl-pack]', 'smart_home')
await page.locator('[data-testid=tpl-list] li input[type=checkbox]').nth(0).check()
await page.locator('[data-testid=tpl-list] li input[type=checkbox]').nth(1).check()
await page.click('[data-testid=tpl-combine-go]')
await page.waitForSelector('[data-testid=tpl-combined], [data-testid=tpl-combine-error]')
check('templates: two chosen templates are combined and checked by the engine', (await page.locator('[data-testid=tpl-combined]').count()) === 1)
await axe('templates')

// ---------------------------------------------------------------- history, audit, export need an approved policy
await open('/studio/history', '[data-testid=history-empty]')
check('history: empty state before any approval', true)
await open('/studio/audit', '[data-testid=audit-empty]')
check('audit: empty state before any decision', true)
await open('/studio/export', '[data-testid=export-empty]')
check('export: empty state before any approval', true)
const a1 = await (await api('/policies/approve', { yog_source: DEMO, english_rules: ['never at night'], note: 'first' })).json()
const a2 = await (await api('/policies/approve', { yog_source: DEMO.replace('H < 6', 'H < 8'), english_rules: ['until 8'], note: 'until 8am' })).json()
check('approving through the API worked', !!a1.id && !!a2.id && a1.id !== a2.id)

await open('/studio/history', '[data-testid=version-list]')
check('history: both versions listed, newest first', (await page.locator('[data-testid=version-list] li').count()) === 2 && /until 8am/.test(await text('[data-testid=version-list] li')))
await page.selectOption('[data-testid=diff-a]', a1.id); await page.selectOption('[data-testid=diff-b]', a2.id)
await page.click('[data-testid=diff-go]')
await page.waitForSelector('[data-testid=diff-result]')
check('history: the diff says which requests change', /different answer/.test(await text('[data-testid=diff-summary]')) && (await page.locator('[data-testid=flips] tbody tr').count()) >= 1)
await page.locator('[data-testid=version-list] li button', { hasText: 'Restore' }).first().click()
await page.waitForSelector('[data-testid=history-restored]')
check('history: restoring saves a third version', (await page.locator('[data-testid=version-list] li').count()) === 3)
await axe('history')

// device -> why link, audit
await open('/device', '[data-testid=device-state]')
await page.click('button:has-text("Unlock front door")')
await page.waitForSelector('[data-testid=why-1]')
await page.click('[data-testid=why-1]')
await page.waitForSelector('[data-testid=why-result]')
check('device: a log row links to the proof of that decision', /ALLOW|DENY/.test(await text('[data-testid=why-verdict]')))
await api('/device/clock', { hour: 3, day: 'tue' })
await api('/device/command', { tool: 'unlock_door', args: { door_id: 'front_door' } })
await open('/studio/audit', '[data-testid=audit-table]')
check('audit: both commands are recorded', (await page.locator('[data-testid=audit-table] tbody tr').count()) === 2)
await page.click('[data-testid=audit-verify]')
await page.waitForSelector('[data-testid=audit-verify-result]')
check('audit: the chain verifies', /Chain intact/.test(await text('[data-testid=audit-verify-result]')))
await page.selectOption('[data-testid=audit-decision]', 'DENY')
await page.waitForFunction(() => document.querySelectorAll('[data-testid=audit-table] tbody tr').length === 1)
check('audit: the DENY filter leaves one row', true)
await page.selectOption('[data-testid=audit-decision]', '')
await page.waitForFunction(() => document.querySelectorAll('[data-testid=audit-table] tbody tr').length === 2)
await page.fill('[data-testid=audit-scrub]', '1')
await page.waitForFunction(() => document.querySelectorAll('[data-testid=audit-table] tbody tr').length === 1)
check('audit: the slider replays the day up to a point', true)
const dl = page.waitForEvent('download')
await page.click('[data-testid=audit-csv]')
check('audit: CSV downloads', (await dl).suggestedFilename() === 'yog_audit_log.csv')
await axe('audit')

// ---------------------------------------------------------------- replay
await open('/studio/replay', '[data-testid=tool-page-replay]')
await page.click('[data-testid=replay-sample]')
await page.waitForFunction(() => document.querySelector('[data-testid=replay-text]')?.value.includes('unlock_door'))
await page.click('[data-testid=replay-run]')
await page.waitForSelector('[data-testid=replay-summary]')
check('replay: the sample day is decided (12 calls)', /of 12 calls/.test(await text('[data-testid=replay-summary]')))
await page.check('[data-testid=replay-compare]')
await page.waitForSelector('[data-testid=policy-picker] >> nth=1')
await page.locator('[data-testid=policy-select]').nth(1).selectOption(a2.id)
await page.locator('[data-testid=policy-select]').nth(0).selectOption(a1.id)
await page.click('[data-testid=replay-run]')
await page.waitForFunction(() => document.querySelector('[data-testid=replay-changed]'))
check('replay: comparing two versions marks the changed call', Number(await text('[data-testid=replay-changed]')) === 1 && (await page.locator('[data-changed=true]').count()) === 1)
await page.click('[data-testid=replay-audit]')
await page.waitForFunction(() => /of 2 calls/.test(document.querySelector('[data-testid=replay-summary]')?.textContent ?? ''))
check('replay: the audit log can be replayed', true)
await axe('replay')

// ---------------------------------------------------------------- sdk
await open('/studio/sdk', '[data-testid=sdk-snippet]')
await page.waitForFunction(() => document.querySelector('[data-testid=sdk-download]') && !document.querySelector('[data-testid=sdk-download]').disabled)
await page.fill('[data-testid=try-hour]', '3')
await page.click('[data-testid=try-run]')
await page.waitForSelector('[data-testid=try-result]')
check('sdk: asking the guard about a 3am unlock says DENY', /DENY/.test(await text('[data-testid=try-result]')))
await page.fill('[data-testid=try-args]', '{bad')
await page.click('[data-testid=try-run]')
await page.waitForSelector('[data-testid=tool-error]')
check('sdk: invalid JSON arguments are explained', /not valid JSON/.test(await text('[data-testid=tool-error]')))
const dl2 = page.waitForEvent('download')
await page.click('[data-testid=sdk-download]')
check('sdk: yog_runtime.py downloads', (await dl2).suggestedFilename() === 'yog_runtime.py')
await axe('sdk')

// ---------------------------------------------------------------- export
await open('/studio/export', '[data-testid=export-files]')
check('export: the file list is shown for the approved policy', (await page.locator('[data-testid=export-files] li').count()) === 4)
const dl3 = page.waitForEvent('download')
await page.click('[data-testid=export-go]')
const got = await dl3
check('export: the zip downloads', /^yog_export_p-.*\.zip$/.test(got.suggestedFilename()))
await page.waitForSelector('[data-testid=export-done]')
await page.selectOption('[data-testid=policy-select]', 'demo').catch(() => {})
await axe('export')

// ---------------------------------------------------------------- scorecard
await open('/studio/scorecard', '[data-testid=scorecard-result]')
check('scorecard: six honest metrics and a headline', (await page.locator('[data-testid^=metric-]').count()) === 6 && /checks look good/.test(await text('[data-testid=scorecard-headline]')))
check('scorecard: a check that was not measured says so', (await page.getAttribute('[data-testid=metric-tools]', 'data-status')) === 'todo' || (await page.getAttribute('[data-testid=metric-scenarios]', 'data-status')) === 'todo')
await axe('scorecard')

// ---------------------------------------------------------------- hub, how-it-works, navigation
await open('/studio', '[data-testid=tool-count]')
check('hub: 17 tools, all ready', /17 tools, all ready/.test(await text('[data-testid=tool-count]')) && (await page.locator('[data-testid^=tool-open-]').count()) === 17)
check('hub: knows an approved policy exists and links to its scorecard', (await page.locator('[data-testid=hub-approved]').count()) === 1)
for (const id of ['why', 'map', 'gaps', 'redteam', 'strength', 'templates', 'history', 'audit', 'replay', 'sdk', 'export', 'scorecard']) {
  await page.goto(BASE + '/studio'); await page.waitForSelector(`[data-testid=tool-open-${id}]`)
  await page.click(`[data-testid=tool-open-${id}]`)
  await page.waitForSelector(`[data-testid=tool-page-${id}]`, { timeout: 15000 })
  check(`hub -> ${id} opens its page`, true)
}
await open('/how-it-works', '[data-testid=how-tools]')
check('how-it-works: lists all 17 tools', (await page.locator('[data-testid=how-tools] li').count()) === 17)
await axe('hub')

// ---------------------------------------------------------------- phones
// each page is checked in the state where it is widest: after its result is on screen (an earlier version of this check
// only looked at the empty page and missed a 400px overflow caused by the policy listing)
const WIDE = {
  '/studio': async (p) => p.waitForSelector('[data-testid=tool-count]'),
  '/studio/why?action=can_unlock_door&ctx=hour(now%2C%203)': async (p) => p.waitForSelector('[data-testid=why-result]'),
  '/studio/map': async (p) => { await p.waitForFunction(() => document.querySelectorAll('[data-testid=map-action] option').length > 3); await p.click('[data-testid=map-run]'); await p.waitForSelector('[data-testid=map-result]') },
  '/studio/gaps': async (p) => p.waitForSelector('[data-testid=gaps-result]'),
  '/studio/red-team': async (p) => { await p.waitForFunction(() => !document.querySelector('[data-testid=add-invariant]')?.disabled); await p.click('[data-testid=add-invariant]'); await p.click('[data-testid=redteam-run]'); await p.waitForSelector('[data-testid=redteam-result]') },
  '/studio/strength': async (p) => { await p.click('[data-testid=strength-run]'); await p.waitForSelector('[data-testid=strength-result]') },
  '/studio/templates': async (p) => { await p.waitForFunction(() => document.querySelectorAll('[data-testid=tpl-list] li').length >= 60); await p.locator('[data-testid=tpl-list] li button', { hasText: 'Show the YOG' }).first().click() },
  '/studio/history': async (p) => { await p.waitForSelector('[data-testid=version-list]'); await p.selectOption('[data-testid=diff-a]', { index: 1 }); await p.click('[data-testid=diff-go]'); await p.waitForSelector('[data-testid=diff-result]') },
  '/studio/audit': async (p) => p.waitForSelector('[data-testid=audit-table]'),
  '/studio/replay': async (p) => { await p.click('[data-testid=replay-sample]'); await p.waitForFunction(() => document.querySelector('[data-testid=replay-text]')?.value.includes('unlock_door')); await p.click('[data-testid=replay-run]'); await p.waitForSelector('[data-testid=replay-table]') },
  '/studio/sdk': async (p) => { await p.waitForSelector('[data-testid=sdk-snippet]'); await p.click('[data-testid=try-run]'); await p.waitForSelector('[data-testid=try-result]'); await p.locator('details summary').click() },
  '/studio/export': async (p) => p.waitForSelector('[data-testid=export-files]'),
  '/studio/scorecard': async (p) => p.waitForSelector('[data-testid=scorecard-result]'),
}
for (const w of [375, 768]) {
  const p = await (await b.newContext({ viewport: { width: w, height: 800 } })).newPage()
  // this visitor has two approved versions and some device history, so history, audit and export show real data
  await p.request.post(BASE + '/api/policies/approve', { data: { yog_source: DEMO, english_rules: ['never at night'], note: 'first' } })
  await p.request.post(BASE + '/api/policies/approve', { data: { yog_source: DEMO.replace('H < 6', 'H < 8'), english_rules: ['until 8'], note: 'until 8am' } })
  await p.request.post(BASE + '/api/device/clock', { data: { hour: 3, day: 'tue' } })
  await p.request.post(BASE + '/api/device/command', { data: { tool: 'unlock_door', args: { door_id: 'front_door' } } })
  for (const [route, ready] of Object.entries(WIDE)) {
    await p.goto(BASE + route)
    try { await ready(p); await p.waitForTimeout(400) } catch (e) { check(`ready ${route} at ${w}px`, false, String(e.message).split('\n')[0]); continue }
    const o = await overflowX(p)
    check(`no sideways scroll at ${w}px on ${route.split('?')[0]} (result showing)`, o <= 0, `overflow ${o}px`)
  }
}
check('no console or page errors anywhere', errors.length === 0, errors.slice(0, 3).join(' | '))
await b.close()
process.exit(summary() ? 1 : 0)
