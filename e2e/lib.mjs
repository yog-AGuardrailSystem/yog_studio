import { chromium } from 'playwright-core'
import { existsSync } from 'node:fs'

export const BASE = process.env.BASE || 'http://localhost:5173'
let pass = 0, fail = 0
export function check(name, ok, extra = '') {
  if (ok) { pass++; console.log('PASS', name) } else { fail++; console.log('FAIL', name, extra) }
}
export const summary = () => { console.log(`\n${pass} passed, ${fail} failed`); return fail }

const CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser',
].filter(Boolean)

/** Uses an installed Chrome/Chromium (CI installs google-chrome-stable); software GL so three.js scenes render headless. */
export async function launch() {
  const executablePath = CANDIDATES.find((p) => existsSync(p))
  return chromium.launch({
    executablePath, headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'],
  })
}
/** collects uncaught errors and console errors on a page */
export function watch(page, bucket) {
  page.on('pageerror', (e) => bucket.push('pageerror: ' + e.message))
  page.on('console', (m) => { if (m.type() === 'error') bucket.push('console: ' + m.text()) })
}
export const overflowX = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
