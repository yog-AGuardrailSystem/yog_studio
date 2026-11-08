// Motion tour: counts distinct registered motion behaviours (data-motion ids) seen while visiting the site,
// checks the pause control really stops animation, and that reduced-motion shows final states.
// Baseline before the motion round (measured): ~30 behaviours. Target: >= TARGET.
import { BASE, check, launch, summary, watch } from './lib.mjs'

const TARGET = Number(process.env.MOTION_TARGET || 300)
const b = await launch()
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
page.on('dialog', (d) => d.accept())
const errors = []
watch(page, errors)
const seen = new Set()
const harvest = async () => {
  const ids = await page.evaluate(() => [...document.querySelectorAll('[data-motion]')].map((e) => e.getAttribute('data-motion')))
  ids.forEach((i) => seen.add(i))
}
const scrollAll = async () => {
  const h = await page.evaluate(() => document.documentElement.scrollHeight)
  for (let y = 0; y < h; y += 500) { await page.evaluate((v) => window.scrollTo(0, v), y); await page.waitForTimeout(260); await harvest() }
}

// ---- landing
await page.goto(BASE + '/')
await page.waitForSelector('[data-testid=explorer][data-online=true]', { timeout: 20000 })
await page.waitForSelector('[data-testid=compiler-scenes][data-live=true]', { timeout: 20000, state: 'attached' })
await page.mouse.move(600, 400); await page.mouse.click(600, 400)
await scrollAll()
const landing = seen.size
check('landing registers many behaviours', landing >= 120, String(landing))
check('four compiler scenes render from real compiler output', (await page.locator('[data-testid^=scene-]').count()) === 4)
check('pipeline conveyor runs once visible', (await page.getByTestId('pipeline-flow').getAttribute('data-running')) === 'true')

// ---- how it works
await page.goto(BASE + '/how-it-works')
await page.waitForSelector('[data-testid=stage]')
await scrollAll()

// ---- workbench
await page.goto(BASE + '/studio')
await page.waitForSelector('[data-testid=yog-editor] .monaco-editor', { timeout: 20000 })
await page.getByTestId('tour-skip').click().catch(() => {})
for (const tab of ['Tests', 'Tokens', 'AST', 'Checks', 'Readback']) {
  await page.getByTestId(`tab-${tab}`).click()
  await page.waitForTimeout(500)
  await harvest()
}
await page.getByTestId('tab-Tests').click()
await page.getByTestId('query-row').first().click().catch(() => {})
await harvest()
for (const g of ['R', 'A', 'D']) { await page.getByTestId(`example-${g}`).click(); await page.waitForTimeout(700); await harvest() }
await page.getByTestId('tab-Assist').click()
await page.getByTestId('assist-input').fill('Only admins may delete a database.')
await page.getByTestId('assist-find').click()
await page.waitForSelector('[data-testid=retrieved-list] li'); await harvest()
await page.getByTestId('assist-draft').click()
await page.waitForSelector('[data-testid=draft-box]', { timeout: 20000 }); await harvest()
await page.keyboard.press('Control+K'); await page.waitForTimeout(300); await harvest(); await page.keyboard.press('Escape')

const total = seen.size
console.log(`distinct motion behaviours seen: ${total} (landing alone: ${landing})`)
const families = {}
for (const id of seen) { const f = id.split(':').slice(0, 2).join(':'); families[f] = (families[f] || 0) + 1 }
console.log(Object.entries(families).sort((a, c) => c[1] - a[1]).slice(0, 12).map(([k, v]) => `${k}=${v}`).join('  '))
check(`at least ${TARGET} distinct registered behaviours`, total >= TARGET, String(total))

// ---- pause control stops animation
await page.goto(BASE + '/')
await page.waitForSelector('[data-testid=motion-toggle]')
await page.waitForTimeout(1500)
const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running').length)
check('animations are running by default', running > 0, String(running))
await page.getByTestId('motion-toggle').click()
await page.waitForTimeout(400)
check('toggle marks the page paused', (await page.evaluate(() => document.documentElement.dataset.motion)) === 'paused')
const after = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running' && a.effect?.getComputedTiming().iterations === Infinity).length)
check('no infinite animation keeps running when paused', after === 0, String(after))
await page.reload()
await page.waitForTimeout(600)
check('the choice is remembered after reload', (await page.evaluate(() => document.documentElement.dataset.motion)) === 'paused')
check('particle canvas element exists (drawing is skipped when paused)', (await page.locator('[data-motion="fx:particles"]').count()) === 1)
await page.getByTestId('motion-toggle').click()

// ---- OS reduced motion
const rctx = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
const rp = await rctx.newPage()
await rp.goto(BASE + '/')
await rp.waitForSelector('[data-testid=compiler-scenes][data-live=true]', { timeout: 20000, state: 'attached' })
await rp.waitForTimeout(800)
const infinite = await rp.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running' && a.effect?.getComputedTiming().iterations === Infinity).length)
check('OS reduced-motion: no endless animation', infinite === 0, String(infinite))
check('OS reduced-motion: scene content still shown', (await rp.locator('[data-motion^="scene:lexer:tok:"]').count()) > 0)

const real = errors.filter((e) => !/favicon|ResizeObserver|WebGL|GPU/i.test(e))
check('no console errors', real.length === 0, real.slice(0, 3).join(' | '))
await b.close()
process.exit(summary() ? 1 : 0)
