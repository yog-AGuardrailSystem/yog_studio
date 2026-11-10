// The black + gold hero: a gold orb of dots with the YOG logo living inside it. Needs only the frontend (Vite on :5173 or BASE); no backend.
import { BASE, check, launch, overflowX, summary } from './lib.mjs'

const b = await launch()
const errors = []
const watchErrors = (page) => {
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  // a stopped backend shows up as failed /api requests; those are not what this suite is about
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()) })
}
const G = '[data-testid=hero-globe]'
const attr = (page, name) => page.getAttribute(G, name)
const yaw = async (page) => parseFloat(await attr(page, 'data-yaw'))
const ready = (page) => page.waitForFunction(() => document.querySelector('[data-testid=hero-globe]')?.dataset.ready === 'true', null, { timeout: 30000 }).then(() => true).catch(() => false)
async function until(page, fn, ms = 20000) {
  const end = Date.now() + ms
  while (Date.now() < end) { if (await fn()) return true; await page.waitForTimeout(120) }
  return false
}
/** counts pixels matching `test` (r,g,b) inside a rectangle (fractions of the globe box) of a screenshot, decoded in the page */
async function count(page, test, rect = [0, 0, 1, 1]) {
  const buf = await page.locator(G).screenshot()
  return page.evaluate(async ([b64, src, r]) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode()
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height
    const x = c.getContext('2d'); x.drawImage(img, 0, 0)
    const f = new Function('r', 'g', 'b', 'return ' + src)
    const x0 = Math.floor(r[0] * c.width), y0 = Math.floor(r[1] * c.height), w = Math.floor((r[2] - r[0]) * c.width), h = Math.floor((r[3] - r[1]) * c.height)
    const d = x.getImageData(x0, y0, w, h).data
    let n = 0
    for (let i = 0; i < d.length; i += 4) if (f(d[i], d[i + 1], d[i + 2])) n++
    return n
  }, [buf.toString('base64'), test, rect])
}
const GOLD = 'r > 150 && g > 90 && b < 170 && r > b + 50'

// ---- desktop: landing, interaction
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
check('the globe is ready (WebGL)', await ready(page))
check('on landing it starts turning from side-on to front-on', await until(page, async () => (await attr(page, 'data-phase')) === 'reveal', 6000))
check('then keeps turning slowly on its own', await until(page, async () => (await attr(page, 'data-phase')) === 'orbit', 15000))
check('the orb is drawn in gold dots', (await count(page, GOLD)) > 1500)
const y0 = await yaw(page); await page.waitForTimeout(2200)
check('it turns by itself', Math.abs((await yaw(page)) - y0) > 0.03, `${y0} -> ${await yaw(page)}`)

// the logo is always inside: turn it to face us and the letters are bright dots in the middle of the orb
await page.getByTestId('hero-logo-btn').focus(); await page.keyboard.press('Enter')
check('"Show the logo" turns the orb to face the viewer (keyboard)', await until(page, async () => Math.abs(await yaw(page)) < 0.2, 8000))
await page.mouse.move(5, 5); await page.waitForTimeout(600)
const middle = [0.3, 0.3, 0.7, 0.6]
const WHITE = 'r > 215 && g > 190 && b > 130'
const faceOn = await count(page, WHITE, middle)
check('front-on, the YOG letters are a bright cluster of dots in the middle', faceOn > 400, String(faceOn))

// drag turns it side-on: the logo becomes a band, and nothing is rebuilt (same dots)
const box = await page.locator(G).boundingBox()
await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5)
const before = await yaw(page)
await page.mouse.down(); await page.mouse.move(box.x + box.width * 0.5 + 330, box.y + box.height * 0.5, { steps: 16 }); await page.mouse.up()
await page.waitForTimeout(500)
check('dragging turns the orb', Math.abs((await yaw(page)) - before) > 0.6, `${before} -> ${await yaw(page)}`)
check('and it stays in orbit (no scripted sequence takes over)', (await attr(page, 'data-phase')) === 'orbit')
const sideOn = await count(page, WHITE, middle)
check('the bright core is still there from another angle (same dots, nothing rearranged)', sideOn > 150, String(sideOn))

// hover, click, right button
await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.4); await page.waitForTimeout(600)
check('hovering marks the orb as hovered', (await attr(page, 'data-hover')) === 'true')
const imp0 = parseInt(await attr(page, 'data-impacts'))
await page.mouse.click(box.x + box.width * 0.55, box.y + box.height * 0.45)
await page.waitForTimeout(500)
check('a click sends a ripple (and a burst of dots)', parseInt(await attr(page, 'data-impacts')) === imp0 + 1)
await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5, { button: 'right' })
await page.waitForTimeout(300)
check('the right button does nothing', parseInt(await attr(page, 'data-impacts')) === imp0 + 1)
await page.mouse.move(5, 5); await page.waitForTimeout(700)
check('leaving clears the hover', (await attr(page, 'data-hover')) === 'false')

// ---- look
const look = await page.evaluate(() => ({
  mkt: getComputedStyle(document.querySelector('.mkt')).backgroundColor,
  btn: getComputedStyle(document.querySelector('.mkt .btn-primary')).backgroundColor,
  net: !!document.querySelector('[data-motion="fx:particles"]'),
}))
check('the marketing ground is pure black', look.mkt === 'rgb(0, 0, 0)', look.mkt)
check('the primary button is gold', look.btn === 'rgb(245, 185, 66)', look.btn)
check('the floating connected dots are still there', look.net)

// ---- one WebGL scene at first, the decision gate only when you get near it
check('the decision gate is not loaded at first', (await page.locator('[data-testid=gate-scene]').count()) === 0)
await page.locator('[data-testid=hero-visual]').scrollIntoViewIfNeeded()
check('the decision gate loads when you scroll to it', await page.waitForSelector('[data-testid=gate-scene]', { timeout: 15000 }).then(() => true).catch(() => false))

// ---- pause control and reduced motion give one still frame facing the viewer
await page.evaluate(() => window.scrollTo(0, 0))
await page.getByTestId('motion-toggle').click()
await page.waitForTimeout(1500)
const still = await yaw(page)
await page.waitForTimeout(1500)
const after = await yaw(page)
check('pausing shows a still frame facing the viewer', (await attr(page, 'data-calm')) === 'true' && Math.abs(still) < 0.05 && after === still, `calm=${await attr(page, 'data-calm')} still=${still} after=${after}`)
await page.getByTestId('motion-toggle').click()
await ctx.close()

const rm = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
const prm = await rm.newPage(); watchErrors(prm)
await prm.goto(BASE + '/'); await prm.waitForSelector(G)
await ready(prm); await prm.waitForTimeout(1500)
check('OS reduced motion shows the still frame', (await attr(prm, 'data-calm')) === 'true' && Math.abs(await yaw(prm)) < 0.05)
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
