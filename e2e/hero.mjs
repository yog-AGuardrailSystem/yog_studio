// The black + gold hero and its interactive globe. Needs only the frontend (Vite on :5173 or BASE); no backend.
import { BASE, check, launch, overflowX, summary } from './lib.mjs'

const b = await launch()
const errors = []
const watchErrors = (page) => {
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  // a stopped backend shows up as failed /api requests; those are not what this suite is about
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()) })
}
const G = '[data-testid=hero-globe]'
const phase = (page) => page.getAttribute(G, 'data-phase')
async function until(page, name, ms = 25000) {
  const end = Date.now() + ms
  while (Date.now() < end) { if ((await phase(page)) === name) return true; await page.waitForTimeout(120) }
  return false
}
/** counts gold-looking pixels in a screenshot of the globe, with no image library: decode it in the page */
async function goldPixels(page) {
  const buf = await page.locator(G).screenshot()
  return page.evaluate(async (b64) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode()
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height
    const x = c.getContext('2d'); x.drawImage(img, 0, 0)
    const d = x.getImageData(0, 0, c.width, c.height).data
    let n = 0
    for (let i = 0; i < d.length; i += 4) if (d[i] > 170 && d[i + 1] > 110 && d[i + 2] < 150 && d[i] > d[i + 2] + 60) n++
    return n
  }, buf.toString('base64'))
}

// ---- desktop: the sequence, the look, the interaction
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
watchErrors(page)
await page.goto(BASE + '/')
await page.waitForSelector(G)
check('the globe is in the hero, to the right of the headline', await page.evaluate(() => {
  const g = document.querySelector('[data-testid=hero-globe]').getBoundingClientRect()
  const h = document.querySelector('#hero h1').getBoundingClientRect()
  return g.left >= h.right - 40 && g.top < 500
}))
check('the globe is ready (WebGL)', await page.waitForFunction(() => document.querySelector('[data-testid=hero-globe]')?.dataset.ready === 'true', null, { timeout: 20000 }).then(() => true).catch(() => false))
check('dots gather, then form the logo', await until(page, 'logo'))
check('the logo is drawn in gold dots', (await goldPixels(page)) > 1500, String(await goldPixels(page)))
check('then it melts into the globe', await until(page, 'globe'))
check('the globe is drawn in gold dots', (await goldPixels(page)) > 800)

const box = await page.locator(G).boundingBox()
await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.4)
await page.mouse.down(); await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.5, { steps: 10 }); await page.mouse.up()
check('dragging does not form the logo', (await phase(page)) === 'globe')
await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5)
check('a click re-forms the logo', await until(page, 'logo', 8000))
check('while the cursor rests on it the logo stays (hover-dwell)', await page.waitForTimeout(5500).then(() => phase(page)).then((p) => p === 'logo'))
await page.mouse.move(5, 5)
check('and it melts back into the globe once the cursor leaves', await until(page, 'globe', 15000))
await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5)
check('hovering for a moment re-forms the logo', await until(page, 'logo', 8000))
await page.mouse.move(5, 5)
check('leaving melts it back', await until(page, 'globe', 15000))
await page.getByTestId('hero-logo-btn').focus()
await page.keyboard.press('Enter')
check('the "Show the logo" button works from the keyboard', await until(page, 'logo', 8000))

// ---- look
const look = await page.evaluate(() => ({
  mkt: getComputedStyle(document.querySelector('.mkt')).backgroundColor,
  btn: getComputedStyle(document.querySelector('.mkt .btn-primary')).backgroundColor,
  rail: !!document.querySelector('[data-motion="fx:particles"]'),
}))
check('the marketing ground is pure black', look.mkt === 'rgb(0, 0, 0)', look.mkt)
check('the primary button is gold', look.btn === 'rgb(245, 185, 66)', look.btn)
check('the floating connected dots are still there', look.rail)

// ---- one WebGL scene at first, the decision gate only when you get near it
check('only the globe has a WebGL canvas at first', (await page.locator('canvas').count()) >= 1 && (await page.locator('[data-testid=gate-scene]').count()) === 0)
await page.locator('[data-testid=hero-visual]').scrollIntoViewIfNeeded()
check('the decision gate loads when you scroll to it', await page.waitForSelector('[data-testid=gate-scene]', { timeout: 15000 }).then(() => true).catch(() => false))

// ---- pause control and reduced motion give one still frame with the logo formed
await page.evaluate(() => window.scrollTo(0, 0))
await page.getByTestId('motion-toggle').click()
await page.waitForTimeout(1500)
check('pausing shows the logo as a still frame', (await phase(page)) === 'logo' && (await page.getAttribute(G, 'data-calm')) === 'true')
await page.getByTestId('motion-toggle').click()
await ctx.close()

const rm = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
const prm = await rm.newPage(); watchErrors(prm)
await prm.goto(BASE + '/'); await prm.waitForSelector(G)
await prm.waitForTimeout(2500)
check('OS reduced motion shows the still logo', (await prm.getAttribute(G, 'data-calm')) === 'true' && (await phase(prm)) === 'logo')
await rm.close()

// ---- no WebGL: a static gold wordmark
const fx = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage(); watchErrors(fx)
await fx.goto(BASE + '/?fx=off'); await fx.waitForSelector('[data-testid=hero-globe-fallback]')
check('without WebGL a static wordmark replaces the globe', (await fx.getAttribute(G, 'data-ready')) === 'fallback')
await fx.context().close()

// ---- small screens
for (const [w, h] of [[375, 800], [768, 900]]) {
  const p = await (await b.newContext({ viewport: { width: w, height: h } })).newPage(); watchErrors(p)
  await p.goto(BASE + '/'); await p.waitForSelector(G); await p.waitForTimeout(1200)
  check(`no horizontal overflow at ${w}px`, (await overflowX(p)) <= 1, String(await overflowX(p)))
  check(`the globe is still there at ${w}px`, (await p.locator(G).boundingBox()).height > 200)
  await p.context().close()
}

// ---- other pages
const how = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage(); watchErrors(how)
await how.goto(BASE + '/how-it-works'); await how.waitForTimeout(1500)
check('How it works is black and gold too', (await how.evaluate(() => getComputedStyle(document.querySelector('.mkt')).backgroundColor)) === 'rgb(0, 0, 0)')
const studio = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage(); watchErrors(studio)
await studio.goto(BASE + '/studio'); await studio.waitForSelector('[data-testid=workbench]')
check('the Studio workbench keeps its own dark blue look', (await studio.evaluate(() => getComputedStyle(document.querySelector('.studio-dark')).backgroundColor)) === 'rgb(5, 11, 22)')

check('no page or console errors', errors.length === 0, errors.slice(0, 3).join(' | '))
await b.close()
process.exit(summary() ? 1 : 0)
