// The Studio hub (/studio): lists every tool, ready ones open, planned ones are honest, old share links still work. Needs only the frontend.
import { BASE, check, launch, overflowX, summary } from './lib.mjs'

const b = await launch()
const errors = []
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()) })

await page.goto(BASE + '/studio')
await page.waitForSelector('[data-testid=tool-count]')
const names = await page.locator('[data-testid^=tool-name-]').allTextContents()
check('hub lists 17 tools', names.length === 17, String(names.length))
check('five groups', (await page.locator('[data-testid^=group-]').count()) === 5)
check('black landing theme (.mkt)', (await page.locator('.mkt').count()) === 1)
const counts = await page.getByTestId('tool-count').textContent()
check('count line matches the page', /17 tools, all ready/.test(counts ?? ''), counts)
check('every card explains how it works', (await page.locator('li').getByText('How it works', { exact: true }).count()) === 17)
check('no tool is marked planned', (await page.locator('[data-testid^=tool-soon-]').count()) === 0)

// ---- the 3D boxes ----
const GROUP_TOOLS = { build: ['workbench', 'agent', 'templates'], understand: ['why', 'map', 'gaps'], test: ['evaluate', 'redteam', 'strength', 'replay'], ship: ['patch', 'sdk', 'export'], operate: ['device', 'audit', 'history', 'scorecard'] }
await page.waitForSelector('[data-testid=hub-stage][data-ready=scene]', { timeout: 60000 })
check('the 3D scene is running', true)
check('five boxes, named as the stages', (await page.locator('[data-testid^=box-]').count()) === 5 &&
  JSON.stringify(await page.locator('[data-testid^=box-]').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label').split(':')[0]))) === JSON.stringify(['Build a policy', 'Understand it', 'Test it', 'Ship it', 'Operate it']))
const sized = await page.locator('[data-testid^=box-]').evaluateAll((els) => els.every((e) => { const r = e.getBoundingClientRect(); return r.width > 80 && r.height > 40 }))
check('each box button sits over its 3D box', sized)
await page.getByTestId('box-test').hover({ force: true })
await page.waitForTimeout(300)
check('hovering a box names it', /Test it/.test(await page.getByTestId('hub-caption').textContent()))

for (const [g, tools] of Object.entries(GROUP_TOOLS)) {
  await page.goto(BASE + '/studio'); await page.waitForSelector('[data-testid=hub-stage][data-ready=scene]', { timeout: 60000 })
  await page.getByTestId(`box-${g}`).click({ force: true })
  await page.waitForSelector(`[data-testid=card-open-${tools[0]}]`, { timeout: 90000 })
  const got = await page.locator('[data-testid^=card-open-]').evaluateAll((els) => els.map((e) => e.getAttribute('data-testid').slice(10)))
  check(`box ${g} opens with its ${tools.length} cards`, JSON.stringify(got) === JSON.stringify(tools), got.join(','))
  check(`box ${g} puts #box=${g} in the address`, page.url().endsWith(`#box=${g}`))
}

await page.goto(BASE + '/studio'); await page.waitForSelector('[data-testid=hub-stage][data-ready=scene]', { timeout: 60000 })
await page.getByTestId('box-test').click({ force: true })
await page.waitForSelector('[data-testid=card-open-redteam]', { timeout: 90000 })
await page.getByTestId('card-open-redteam').hover({ force: true })
await page.waitForTimeout(300)
check('hovering a card shows its name and purpose', /Red-Team/.test(await page.getByTestId('hub-caption').textContent()))
await page.getByTestId('card-open-redteam').click({ force: true })
await page.waitForURL('**/studio/red-team')
check('a card opens its tool', page.url().endsWith('/studio/red-team'))
await page.goBack()
await page.waitForSelector('[data-testid=card-open-redteam]', { timeout: 90000 })
check('browser Back from a tool returns to the open box', page.url().endsWith('#box=test'))
await page.keyboard.press('Escape')
await page.waitForSelector('[data-testid=box-test]', { timeout: 90000 })
check('Escape closes the box', (await page.locator('[data-testid^=card-open-]').count()) === 0 && !page.url().includes('#box='))

await page.goto(BASE + '/studio#box=ship')
await page.waitForSelector('[data-testid=card-open-patch]', { timeout: 90000 })
check('a #box= link opens that box', (await page.locator('[data-testid^=card-open-]').count()) === 3)
await page.getByTestId('hub-back').click()
await page.waitForSelector('[data-testid=box-ship]', { timeout: 90000 })
check('All boxes goes back', (await page.locator('[data-testid^=card-open-]').count()) === 0)

// keyboard only: focus a box, Enter opens it and focus moves to its first card
await page.keyboard.press('Shift')                           // a key press makes focus "visible", as for a real keyboard user
await page.getByTestId('box-ship').focus()
await page.keyboard.press('Enter')
await page.waitForSelector('[data-testid=card-open-patch]', { timeout: 90000 })
// the card takes focus once it has risen into view (slow on a software renderer)
const focused = await page.waitForFunction(() => document.activeElement?.getAttribute('data-testid') === 'card-open-patch', null, { timeout: 30000 }).then(() => true).catch(() => false)
check('Enter opens a box and focuses its first card', focused)
await page.keyboard.press('Escape')

// the YOG monogram
const about = page.getByTestId('yog-about')
check('About is closed at first', !(await about.isVisible()))
await page.getByTestId('yog-monogram').hover()
await page.waitForSelector('[data-testid=yog-about]', { state: 'visible' })
await page.waitForTimeout(2600)                                  // the text builds in
const aboutText = await about.textContent()
check('hovering YOG opens the About panel', /ALLOW/.test(aboutText) && /DENY/.test(aboutText) && /Build a policy/.test(aboutText))
check('the scene slides aside', (await page.locator('.hub-world').getAttribute('data-aside')) === 'true')
await page.mouse.move(900, 600)
await page.waitForTimeout(700)
check('moving away closes it', !(await about.isVisible()))
await page.getByTestId('yog-monogram').focus()
await page.waitForSelector('[data-testid=yog-about]', { state: 'visible' })
check('keyboard focus opens it too', await about.isVisible())
await page.keyboard.press('Escape')
await page.waitForTimeout(300)
check('Escape closes it', !(await about.isVisible()))

// no WebGL (?fx=off): the same flow on plain tiles
await page.goto(BASE + '/studio?fx=off')
await page.waitForSelector('[data-testid=hub-stage][data-ready=fallback]')
check('without WebGL the five boxes are plain tiles', (await page.locator('.hub-tile').count()) === 5)
await page.getByTestId('box-operate').click({ force: true })
await page.waitForSelector('[data-testid=card-open-device]', { timeout: 90000 })
check('fallback: a box opens its cards', (await page.locator('[data-testid^=card-open-]').count()) === 4)
await page.getByTestId('card-open-device').click({ force: true })
await page.waitForURL('**/device')
check('fallback: a card opens its tool', page.url().endsWith('/device'))

// reduced motion: no camera flight, but the same result
const calmCtx = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
const calmPage = await calmCtx.newPage()
await calmPage.goto(BASE + '/studio')
await calmPage.waitForSelector('[data-testid=hub-stage][data-ready=scene]', { timeout: 60000 })
await calmPage.getByTestId('box-build').click({ force: true })
await calmPage.waitForSelector('[data-testid=card-open-workbench]', { timeout: 90000 })
await calmPage.getByTestId('card-open-workbench').click({ force: true })
await calmPage.waitForURL('**/studio/workbench')
check('reduced motion: box and card still work', calmPage.url().endsWith('/studio/workbench'))

// ---- scramble on hover, gold cursor, cabinets that never sit still, black-and-gold tool pages ----
await page.goto(BASE + '/studio')
await page.waitForSelector('[data-testid=hub-stage][data-ready=scene]', { timeout: 90000 })
// samples a link's visible text right after the pointer arrives, and again after the effect has settled
const scrambleOf = async (p, locator, original) => {
  await p.mouse.move(5, 5)
  await locator.hover()
  const during = await p.waitForFunction(([sel, txt]) => { const el = document.querySelector(sel); return el && el.textContent.trim() !== txt }, [await locator.evaluate((e) => { e.setAttribute('data-probe', '1'); return '[data-probe="1"]' }), original], { timeout: 2000, polling: 10 }).then(() => true).catch(() => false)
  await p.waitForTimeout(900)
  const after = (await locator.textContent()).trim()
  await locator.evaluate((e) => e.removeAttribute('data-probe'))
  return { during, after }
}
for (const [name, loc] of [['How it works', page.locator('.hub-nav').getByRole('link', { name: 'How it works' })], ['All 17 tools explained ↓', page.getByTestId('hub-scroll')]]) {
  const r = await scrambleOf(page, loc, name)
  check(`"${name}" scrambles on hover and settles back`, r.during && r.after === name, JSON.stringify(r))
}
const cursor = await page.evaluate(() => [getComputedStyle(document.documentElement).cursor, getComputedStyle(document.querySelector('.hub-nav a')).cursor])
check('gold cursor on the page and on links', cursor.every((c) => c.includes('url(')), cursor.join(' | '))
const boxRect = () => page.getByTestId('box-test').evaluate((e) => e.style.transform + ' ' + e.style.width)
const r1 = await boxRect(); await page.waitForTimeout(2500); const r2 = await boxRect()
check('the cabinets keep turning slightly (never still)', r1 !== r2, `${r1} -> ${r2}`)
await page.mouse.move(700, 300); await page.mouse.move(900, 500); await page.waitForTimeout(400)
check('moving the cursor through the motes causes no errors', errors.length === 0, errors.slice(0, 2).join(' | '))

await page.goto(BASE + '/studio/red-team')
await page.waitForSelector('[data-testid=all-tools]')
await page.getByRole('button', { name: 'Run Red-Team' }).waitFor({ timeout: 30000 })
const look = await page.evaluate(() => {
  const bg = getComputedStyle(document.querySelector('.studio-dark')).backgroundColor
  const b = [...document.querySelectorAll('button')].find((x) => /Run Red-Team/.test(x.textContent))
  return { bg, btn: b ? getComputedStyle(b).backgroundColor : '' }
})
check('tool pages are black', look.bg === 'rgb(0, 0, 0)', look.bg)
check('tool buttons are gold, not blue', /^rgb\((1[3-9]\d|2\d\d), (9\d|1[0-9]\d|2\d\d), ([0-6]?\d)\)$/.test(look.btn), look.btn)
const tr = await scrambleOf(page, page.getByTestId('all-tools'), 'All tools')
check('tool page links scramble too', tr.during && tr.after === 'All tools', JSON.stringify(tr))

// every ready tool opens a real page (from the list under the stage)
for (const [id, url] of [['workbench', '/studio/workbench'], ['agent', '/agent'], ['evaluate', '/review'], ['patch', '/modify'], ['device', '/device']]) {
  await page.goto(BASE + '/studio')
  await page.getByTestId(`tool-open-${id}`).click()
  await page.waitForURL('**' + url)
  check(`open ${id} -> ${url}`, page.url().endsWith(url))
}

// Studio pages link back to the hub
await page.goto(BASE + '/studio/workbench')
await page.getByTestId('all-tools').click()
await page.waitForURL('**/studio')
check('All tools returns to the hub', page.url().endsWith('/studio'))

// an old share link keeps its program
await page.goto(BASE + '/studio#p=abc')
await page.waitForURL('**/studio/workbench#p=abc')
check('old /studio#p= link forwards to the workbench', page.url().endsWith('/studio/workbench#p=abc'))

// phones: no sideways scroll
for (const w of [375, 768]) {
  const p = await (await b.newContext({ viewport: { width: w, height: 800 } })).newPage()
  await p.goto(BASE + '/studio'); await p.waitForSelector('[data-testid=tool-count]')
  check(`no horizontal overflow at ${w}px`, (await overflowX(p)) <= 0)
}
check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '))
await b.close()
process.exit(summary() ? 1 : 0)
