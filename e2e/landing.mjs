// Landing + how-it-works: live explorer, example cards, finished-product voice (no status wording), no overflow.
import { BASE, check, launch, overflowX, summary, watch } from './lib.mjs'

const BANNED = /\b(in progress|work in progress|coming soon|roadmap|as of|not yet|planned|todo|wip|under construction|beta)\b/i

const b = await launch()
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
const errors = []
watch(page, errors)

await page.goto(BASE + '/')
await page.waitForSelector('[data-testid=explorer]')
await page.waitForSelector('[data-testid=explorer][data-online=true]', { timeout: 20000 })
check('explorer connects to the live compiler', true)
await page.waitForSelector('[data-testid=explorer-result]', { timeout: 10000 })
const first = await page.getByTestId('explorer-result').allInnerTexts()
check('explorer shows real decisions for the sample (ALLOW then DENY)', first.length === 2 && /ALLOW/.test(first[0]) && /DENY/.test(first[1]), first.join(' | '))

await page.getByTestId('explorer-tab-Tokens').click()
await page.waitForSelector('[data-testid=explorer-tokens] span')
check('Tokens tab shows tokens', true)
await page.getByTestId('explorer-tab-Tree').click()
check('Tree tab shows the AST', (await page.getByTestId('explorer-ast').innerText()).includes('clauses'))

// editing changes the answer (not canned output)
await page.getByTestId('explorer-tab-Decisions').click()
const ta = page.getByTestId('explorer-input')
await ta.fill('fact role(bob, viewer)\nallow can_open(U, D):\n    role(U, admin)\nquery can_open(bob, door1)   # -> DENY\n')
await page.waitForFunction(() => /DENY/.test(document.querySelector('[data-testid=explorer-output]')?.textContent || ''), null, { timeout: 8000 })
check('editing the program changes the decision', true)
await ta.fill('fact role(bob, admin)\nallow can_open(U, D):\n    role(U, admin)\nquery can_open(bob, door1)\n')
await page.waitForFunction(() => /ALLOW/.test(document.querySelector('[data-testid=explorer-output]')?.textContent || ''), null, { timeout: 8000 })
check('and changes back when the program changes', true)
await ta.fill('allow can_open(U, D)\n')
await page.waitForFunction(() => /Line|expected|colon|:/.test(document.querySelector('[data-testid=explorer-output]')?.textContent || ''), null, { timeout: 8000 })
check('a broken program shows a plain-English error', true)

// example cards load a group into the explorer
await page.waitForSelector('[data-testid=example-cards] li button:not([disabled])')
const cards = await page.locator('[data-testid=example-cards] li').count()
check('cards for the team examples (A to R) are shown', cards >= 12, String(cards))
await page.getByTestId('card-I').click()
await page.waitForFunction(() => (document.querySelector('[data-testid=explorer-input]')?.value || '').includes('amount'), null, { timeout: 5000 })
check('a card loads its program into the explorer', true)

// finished-product voice
const text = await page.evaluate(() => document.body.innerText)
const hit = text.match(BANNED)
check('landing has no status or roadmap wording', !hit, hit ? hit[0] : '')
check('lexer figures are scoped to the lexer', /lexer only/i.test(text))
await page.goto(BASE + '/how-it-works')
await page.waitForSelector('[data-testid=stage]')
const t2 = await page.evaluate(() => document.body.innerText)
const hit2 = t2.match(BANNED)
check('how-it-works has no status or roadmap wording', !hit2, hit2 ? hit2[0] : '')
check('patch step matches the real modifier (@yog_guard)', !/yog\.check\(/.test(t2))

for (const [w, h] of [[375, 800], [768, 900], [1440, 900]]) {
  await page.setViewportSize({ width: w, height: h })
  for (const path of ['/', '/how-it-works']) {
    await page.goto(BASE + path)
    await page.waitForTimeout(900)
    const o = await overflowX(page)
    check(`no horizontal overflow at ${w}px on ${path}`, o <= 1, String(o))
  }
}
const real = errors.filter((e) => !/favicon|ResizeObserver|WebGL|GPU/i.test(e))
check('no console errors', real.length === 0, real.slice(0, 3).join(' | '))
await b.close()
process.exit(summary() ? 1 : 0)
