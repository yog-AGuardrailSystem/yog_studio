import { chromium } from 'playwright'

const results = []
const ok = (name, pass, extra = '') => { results.push({ name, pass, extra }); console.log(pass ? 'PASS' : 'FAIL', name, extra) }
let browser
try {
  browser = await chromium.launch()
} catch (e) {
  console.log('LAUNCH_FAILED', String(e).slice(0, 300)); process.exit(2)
}
const page = await browser.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
await page.goto('http://localhost:5173/')
await page.waitForSelector('text=YOG Studio')

// W2: upload sample
await page.click('button:has-text("smart_home_mcp.py")')
await page.waitForSelector('[data-testid="detect-badge"]')
ok('W2 detect badge', (await page.textContent('[data-testid="detect-badge"]')).includes('MCP server, 0.95'))
ok('W2 tools table has 5 rows', (await page.locator('[data-testid="tools-table"] tbody tr').count()) === 5)
await page.click('button:has-text("not_an_agent.py")')
await page.waitForSelector('text=Could not tell what kind')
ok('W2 unknown shows manual pick', (await page.locator('input[type=checkbox]').count()) >= 3)
await page.click('button:has-text("smart_home_mcp.py")')
await page.waitForSelector('text=Continue with 5 tools')

// W3/W4: rules page
await page.click('a:has-text("Rules")')
await page.fill('textarea[aria-label="rule 1"]', 'The agent may never unlock the door between 11pm and 6am.')
await page.click('button:has-text("Find similar examples")')
await page.waitForSelector('[data-testid="example-cards"]')
ok('W3 example cards shown', (await page.locator('[data-testid="example-cards"] > div').count()) >= 1)
await page.click('button:has-text("Use prepared demo policy")')
await page.waitForSelector('[data-testid="draft-panel"]')
ok('W4 draft panel compiles', (await page.textContent('[data-testid="draft-panel"]')).includes('compiles'))

// W5/W6: review
await page.click('a:has-text("Review")')
await page.waitForSelector('[data-testid="readback"]')
ok('W5 readback visible', (await page.locator('[data-testid="readback"] > div').count()) > 5)
ok('W5 valid badge', (await page.textContent('[data-testid="valid-badge"]')).includes('compiles'))
ok('W6 Approve disabled before scenarios are run', await page.locator('button:has-text("Approve")').first().isDisabled())
await page.click('button:has-text("Run scenarios")')
await page.waitForSelector('[data-testid="eval-report"]')
ok('W6 eval report shown', (await page.textContent('[data-testid="eval-report"]')).includes('unconfirmed'))
await page.click('button:has-text("Approve")')
await page.waitForSelector('[data-testid="approved-msg"]')
ok('W5 approved message', (await page.textContent('[data-testid="approved-msg"]')).includes('Approved and saved as p-'))

// W7: patch
await page.click('a:has-text("Patch")')
await page.waitForSelector('[data-testid="modify-summary"]')
const sum = await page.textContent('[data-testid="modify-summary"]')
ok('W7 modify summary', sum.includes('5 tool(s) guarded') && sum.includes('0 removed'), sum.trim())

// W8: device
await page.click('a:has-text("Device")')
await page.waitForSelector('[data-testid="device-state"]')
await page.click('button:has-text("Reset")')
await page.waitForFunction(() => document.querySelectorAll('[data-testid="device-log"] tbody tr').length === 0)
await page.click('button:has-text("Run agent demo day")')
await page.waitForFunction(() => document.querySelectorAll('[data-testid="device-log"] tbody tr').length === 7)
const rows = await page.locator('[data-testid="device-log"] tbody tr').count()
ok('W8 demo day logged 7 rows', rows === 7, String(rows))
const txt = await page.textContent('[data-testid="device-log"]')
ok('W8 3am unlock blocked in log', /tue 03:00[\s\S]*DENY/.test(txt))
await page.fill('input[type=number]', '3')
await page.click('button:has-text("Unlock front door")')
await page.waitForSelector('[data-testid="flash"]')
ok('W8 flash says BLOCKED', (await page.textContent('[data-testid="flash"]')).includes('BLOCKED'))
await page.screenshot({ path: 'device.png', fullPage: true })

// W1: check page
await page.click('a:has-text("Check")')
await page.click('button:has-text("Check")')
await page.waitForSelector('[data-testid="result-card"]')
ok('W1 check shows DENY for bob/db1', (await page.textContent('[data-testid="result-card"]')).includes('DENY'))

ok('no uncaught page errors', errors.length === 0, errors.join(' | ').slice(0, 300))
await browser.close()
const failed = results.filter((r) => !r.pass).length
console.log(`SUMMARY ${results.length - failed}/${results.length} passed`)
process.exit(failed ? 1 : 0)
