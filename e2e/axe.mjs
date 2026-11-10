// Accessibility: axe-core colour-contrast (and a few structural rules) on every main screen. Fails on any violation.
import path from 'node:path'
import { BASE, check, launch, summary } from './lib.mjs'

const AXE = path.resolve('node_modules/axe-core/axe.min.js')
const RULES = ['color-contrast', 'button-name', 'link-name', 'label', 'image-alt', 'aria-valid-attr', 'aria-valid-attr-value', 'aria-required-attr']
const b = await launch()
const page = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
page.on('dialog', (d) => d.accept())
const settle = (ms = 900) => page.waitForTimeout(ms)

async function scan(name) {
  await page.addScriptTag({ path: AXE }).catch(() => {})
  const r = await page.evaluate(async (rules) => await window.axe.run(document, { runOnly: { type: 'rule', values: rules } }), RULES)
  const v = r.violations.flatMap((x) => x.nodes.map((n) => `${x.id} ${n.target.join(' ').slice(0, 60)} | ${(n.any[0]?.message || n.all[0]?.message || '').slice(0, 80)}`))
  check(`axe: ${name}`, v.length === 0, '\n   ' + v.slice(0, 5).join('\n   '))
}

await page.goto(BASE + '/')
await page.waitForSelector('[data-testid=explorer][data-online=true]', { timeout: 20000 })
await settle(2200)
await scan('landing top')
for (const sel of ['[data-testid=compiler-scenes]', '[data-testid=pipeline-flow]', '[data-testid=example-cards]', '[data-testid=lexer-facts]']) {
  await page.evaluate((s) => document.querySelector(s)?.scrollIntoView({ block: 'center' }), sel)
  await settle(2200)
  await scan('landing ' + sel)
}
await page.goto(BASE + '/how-it-works'); await page.waitForSelector('[data-testid=stage]'); await settle(1500); await scan('how it works')

await page.goto(BASE + '/studio'); await page.waitForSelector('[data-testid=tool-count]'); await settle(1500); await scan('studio hub')

await page.goto(BASE + '/studio/workbench')
await page.waitForSelector('[data-testid=yog-editor] .monaco-editor', { timeout: 20000 })
await page.getByTestId('tour-skip').click().catch(() => {})
await settle(1200)
await scan('workbench (tour closed)')
for (const tab of ['Checks', 'Tests', 'Tokens', 'AST', 'Readback', 'C lexer', 'Assist', 'Evidence']) {
  await page.getByTestId(`tab-${tab.replace(' ', '-')}`).click()
  await settle(tab === 'Tokens' || tab === 'AST' ? 2400 : 900)       // tokens and tree nodes fade in one after another
  await scan(`workbench ${tab}`)
}
await page.getByTestId('tab-Tests').click(); await page.getByTestId('query-row').nth(1).click(); await settle(700); await scan('workbench why box')
await page.keyboard.press('Control+K'); await settle(500); await scan('command palette'); await page.keyboard.press('Escape')
await page.reload(); await page.waitForSelector('[data-testid=tour]').catch(() => {}); await settle(800); await scan('tour')

await page.goto(BASE + '/agent'); await page.waitForSelector('button:has-text("smart_home_mcp.py")'); await settle(700); await scan('agent upload')
await b.close()
process.exit(summary() ? 1 : 0)
