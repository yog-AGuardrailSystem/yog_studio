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
check('hub lists 13 tools', names.length === 13, String(names.length))
check('five groups', (await page.locator('[data-testid^=group-]').count()) === 5)
check('black landing theme (.mkt)', (await page.locator('.mkt').count()) === 1)
const counts = await page.getByTestId('tool-count').textContent()
check('count line matches the page', /5 ready, 8 planned/.test(counts ?? ''), counts)
check('every card explains how it works', (await page.locator('li').getByText('How it works', { exact: true }).count()) === 13)
check('planned tools have no Open link', (await page.locator('[data-testid^=tool-soon-]').count()) === 8)

// every ready tool opens a real page
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
