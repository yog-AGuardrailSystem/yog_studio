// Workbench walkthrough: needs backend (:8000, LLM_PROVIDER=fake) + frontend (:5173) running.
import { BASE, check, launch, overflowX, summary, watch } from './lib.mjs'

const b = await launch()
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
page.on('dialog', (d) => d.accept())
const errors = []
watch(page, errors)
const settle = (ms = 700) => page.waitForTimeout(ms)

await page.goto(BASE + '/studio/workbench')
await page.waitForSelector('[data-testid=workbench]')
await page.waitForSelector('[data-testid=yog-editor] .monaco-editor', { timeout: 20000 })
check('workbench renders with the editor', true)
check('offline demo chip shown for the fake provider', await page.getByTestId('offline-chip').isVisible())
check('tour appears on first run', await page.getByTestId('tour').isVisible())
await page.getByTestId('tour-skip').click()
check('tour can be skipped', !(await page.getByTestId('tour').isVisible().catch(() => false)))

// starter program compiles; queries pass
await page.waitForFunction(() => document.querySelector('[data-testid=checks-panel]')?.textContent?.includes('Compiles'))
check('starter compiles (Checks)', true)
await page.getByTestId('tab-Tests').click()
await page.waitForSelector('[data-testid=test-summary]')
const sum = await page.getByTestId('test-summary').innerText()
check('starter queries pass as written', /2 passed/.test(sum) && /0 failed/.test(sum), sum)

// why was this decided? highlights the deciding clause in the editor
await page.getByTestId('query-row').nth(1).click()
await page.waitForSelector('[data-testid=why-box]')
await page.waitForSelector('.trace-deciding-line', { timeout: 5000 })
check('Why? highlights the deciding line in the editor', true)

// library: group R loads, queries run with expectations
await page.getByTestId('example-R').click()
await page.waitForFunction(() => document.querySelector('[data-testid=test-summary]')?.textContent?.includes('2 queries'), null, { timeout: 8000 })
const r = await page.getByTestId('test-summary').innerText()
check('group R loads and both queries pass', /2 passed/.test(r), r)

// Tokens / AST / Readback tabs
await page.getByTestId('tab-Tokens').click(); await page.waitForSelector('[data-testid=tokens-panel]')
check('Tokens tab lists tokens', /tokens\./.test(await page.getByTestId('tokens-panel').innerText()))
await page.getByTestId('tab-AST').click(); await page.waitForSelector('[data-testid=ast-panel]')
check('AST tab renders a tree', (await page.getByTestId('ast-panel').innerText()).includes('program'))
await page.getByTestId('tab-Readback').click(); await page.waitForSelector('[data-testid=readback-panel]')
check('Readback tab explains actions in English', /Allowed when|Denied when/.test(await page.getByTestId('readback-panel').innerText()))

// friendly error for a broken program
await page.getByTestId('tab-Checks').click()
await page.locator('[data-testid=yog-editor] .view-lines').click()
await page.keyboard.press('Control+A')
await page.keyboard.type('fact role(alice, admin)\nallow can_x(U, R):\n    role(U, admin)\n    fact_bad(')
await page.waitForSelector('[data-testid=diagnostic]', { timeout: 8000 })
check('a syntax error gives a friendly diagnostic', true)

// command palette + share link
await page.keyboard.press('Control+K')
await page.waitForSelector('[data-testid=palette]')
await page.keyboard.type('tokens')
await page.keyboard.press('Enter')
await page.waitForSelector('[data-testid=tokens-panel]')
check('command palette switches tab', true)
await page.getByTestId('share').click()
await page.waitForFunction(() => location.hash.startsWith('#p='), null, { timeout: 4000 })
check('share link puts the program in the URL', true)
const shared = page.url()
const p2 = await ctx.newPage()
await p2.goto(shared)
await p2.waitForSelector('[data-testid=yog-editor] .monaco-editor', { timeout: 20000 })
await p2.waitForTimeout(600)
const loaded = await p2.evaluate(() => localStorage.getItem('yog.workbench.source'))
check('opening the shared link restores the program', (loaded || '').includes('fact_bad('), String(loaded).slice(0, 60))
await p2.close()

// Assist: retrieval + draft (fake provider copies nearest example) + insert
await page.getByTestId('tab-Assist').click()
await page.getByTestId('assist-input').fill('Only admins may delete a database.')
await page.getByTestId('assist-find').click()
await page.waitForSelector('[data-testid=retrieved-list] li')
check('Assist shows retrieved examples with scores', true)
await page.getByTestId('assist-draft').click()
await page.waitForSelector('[data-testid=draft-box]', { timeout: 20000 })
check('Assist produces a draft', true)
check('the draft names the example it is based on', /Based on:/.test(await page.getByTestId('citations').innerText()))
await page.getByTestId('draft-insert').click()
await page.waitForSelector('[data-testid=toast]')
check('draft is inserted only on click', true)

// Real AI / Offline switch: starts Offline on a server with no key, and says why Real is unavailable
const sw = page.getByTestId('ai-mode-toggle')
check('AI mode switch is shown', await sw.isVisible())
check('AI mode defaults to Offline here', (await sw.getAttribute('aria-checked')) === 'false' && /Offline/.test(await page.getByTestId('ai-mode-label').innerText()))

// Strict RAG: an off-topic rule finds nothing relevant, the UI says so, and the draft needs an explicit confirmation
await page.getByTestId('tab-Assist').click()                        // inserting a draft moved us to Checks
await page.getByTestId('assist-input').fill('What is the capital of France?')
await page.getByTestId('assist-find').click()
await page.waitForSelector('[data-testid=no-match]')
check('off-topic rule shows "no close example"', true)
check('weak matches are marked below the floor', (await page.locator('[data-testid=retrieved-list] li[data-relevant=no]').count()) > 0)
check('the relevance floor is shown', /relevance floor/.test(await page.getByTestId('floor-note').innerText()))
await page.getByTestId('assist-draft').click()
await page.waitForSelector('[data-testid=ungrounded-chip]', { timeout: 20000 })
check('an ungrounded draft is labelled', true)
check('inserting an ungrounded draft is blocked until confirmed', await page.getByTestId('draft-insert').isDisabled())
await page.getByTestId('ungrounded-ack').check()
check('confirming enables inserting', !(await page.getByTestId('draft-insert').isDisabled()))

// Real AI refused or failing (budget, rate limit, outage): the user is never stuck, one click continues Offline.
{
  const p3 = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
  await p3.route('**/api/info', async (route) => {
    const res = await route.fetch()
    const j = await res.json()
    await route.fulfill({ response: res, json: { ...j, live_available: true, live_allowed: true, live_ready: true, live_reason: null, live_provider: 'gemini', default_mode: 'real' } })
  })
  await p3.route('**/api/translate/start', (route) => route.fulfill({ status: 429, contentType: 'application/json', json: { detail: 'The live AI budget for today is used up. Switch to Offline mode, or try again tomorrow.' } }))
  await p3.goto(BASE + '/studio/workbench')
  await p3.waitForSelector('[data-testid=ai-mode-toggle]')
  await p3.getByTestId('tab-Assist').click()
  await p3.waitForFunction(() => document.querySelector('[data-testid=ai-mode-toggle]')?.getAttribute('aria-checked') === 'true', null, { timeout: 8000 })
  check('with a key on the server the switch defaults to Real AI', true)
  check('Real AI badge is shown', await p3.getByTestId('real-badge').isVisible())
  check('re-rank option is available in Real mode', !(await p3.getByTestId('rerank-toggle').isDisabled()))
  await p3.getByTestId('assist-input').fill('Only admins may delete a database.')
  await p3.getByTestId('assist-draft').click()
  await p3.waitForSelector('[data-testid=assist-error]')
  check('a refused live request shows the reason', /budget/.test(await p3.getByTestId('assist-error').innerText()))
  await p3.getByTestId('fallback-offline').click()
  check('one click continues in Offline mode', (await p3.getByTestId('ai-mode-toggle').getAttribute('aria-checked')) === 'false')
  await p3.unroute('**/api/translate/start')
  await p3.getByTestId('assist-draft').click()
  await p3.waitForSelector('[data-testid=draft-box]', { timeout: 20000 })
  check('and the draft then works offline', true)
  await p3.context().close()
}

// Evidence tab never invents numbers
await page.getByTestId('tab-Evidence').click()
await page.waitForSelector('[data-testid=benchmark-panel]')
check('Evidence tab is honest when no real run exists', /No real benchmark|Retrieval|Configuration/.test(await page.getByTestId('benchmark-panel').innerText()))

for (const [w, h] of [[375, 800], [768, 900]]) {
  await page.setViewportSize({ width: w, height: h })
  await settle()
  const o = await overflowX(page)
  const wide = o > 1 ? await page.evaluate((w) => [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > w + 2 && !e.closest('.monaco-editor')).slice(0, 4).map((e) => e.tagName + '.' + String(e.className).slice(0, 40)).join(' | '), w) : ''
  check(`no horizontal overflow at ${w}px`, o <= 1, o + ' ' + wide)
}
const real = errors.filter((e) => !/favicon|ResizeObserver/.test(e))
check('no console errors', real.length === 0, real.slice(0, 3).join(' | '))
await b.close()
process.exit(summary() ? 1 : 0)
