// The PRODUCTION build (app.asgi: API + built UI in one process) under its real security headers.
// Run against `uvicorn app.asgi:app --port 8002` (PROD_BASE overrides).
import { check, launch, summary } from './lib.mjs'

const BASE = process.env.PROD_BASE || 'http://127.0.0.1:8002'
const b = await launch()
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
const problems = []
page.on('console', (m) => { if (m.type() === 'error') problems.push('console: ' + m.text().slice(0, 200)) })
page.on('pageerror', (e) => problems.push('pageerror: ' + String(e).slice(0, 200)))
await page.addInitScript(() => {
  document.addEventListener('securitypolicyviolation', (e) => {
    (window.__csp = window.__csp || []).push(`${e.violatedDirective} blocked ${e.blockedURI}`)
  })
})

// headers
const res = await page.goto(BASE + '/')
const h = res.headers()
check('CSP is enforced', /default-src 'self'/.test(h['content-security-policy'] || ''))
check('clickjacking and sniffing headers set', h['x-frame-options'] === 'DENY' && h['x-content-type-options'] === 'nosniff')
check('no third-party script source (Monaco is self-hosted)', !/jsdelivr|unpkg|cdnjs/.test(h['content-security-policy'] || ''))
const docs = await ctx.request.get(BASE + '/api/docs')
check('API docs page is not public', docs.status() === 404)
check('framing is forbidden by CSP', /frame-ancestors 'none'/.test(h['content-security-policy'] || ''))
const api = await ctx.request.get(BASE + '/api/info')
check('API responses are not cacheable (they can hold a visitor’s data)', (api.headers()['cache-control'] || '') === 'no-store')
const info = await api.json()
check('/info reports the live-AI state', typeof info.live_ready === 'boolean' && 'default_mode' in info)

// every main screen renders with no CSP violation and no console error
for (const path of ['/', '/how-it-works', '/download', '/studio', '/studio#box=test', '/studio/workbench', '/agent']) {
  await page.goto(BASE + path)
  await page.waitForTimeout(path === '/studio/workbench' ? 3500 : 2000)
  const v = await page.evaluate(() => window.__csp || [])
  check(`no CSP violation on ${path}`, v.length === 0, [...new Set(v)].join(' | '))
}

// the editor (Monaco bundled with the app, its worker a same-origin file) and the compiler work in production
await page.goto(BASE + '/studio/workbench')
check('Monaco renders under the policy', await page.waitForSelector('[data-testid=yog-editor] .monaco-editor', { timeout: 20000 }).then(() => true).catch(() => false))
await page.getByTestId('tour-skip').click().catch(() => {})
await page.getByTestId('tab-Tokens').click()
await page.waitForSelector('[data-testid=tokens-panel]', { timeout: 10000 }).then(() => check('live compile works in production', true)).catch(() => check('live compile works in production', false))

// per-visitor session cookie
const cookies = await ctx.cookies()
const sid = cookies.find((c) => c.name === 'yog_sid')
check('visitor session cookie is HttpOnly and SameSite=Lax', !!sid && sid.httpOnly && sid.sameSite === 'Lax')

// two browsers never share approved policies
const other = await b.newContext()
const policy = 'fact role(alice, admin)\nallow can_x(U, R):\n    role(U, admin)\n'
const mine = await ctx.request.post(BASE + '/api/policies/approve', { data: { yog_source: policy, english_rules: ['x'] } })
check('a visitor can approve a policy', mine.ok(), String(mine.status()))
const mineList = await (await ctx.request.get(BASE + '/api/policies')).json()
const theirList = await (await other.request.get(BASE + '/api/policies')).json()
check('their own policies are listed', mineList.length >= 1)
check('another visitor sees none of them', theirList.length === 0, JSON.stringify(theirList).slice(0, 80))

check('no console or page errors', problems.length === 0, problems.join(' | '))
await b.close()
process.exit(summary() ? 1 : 0)
