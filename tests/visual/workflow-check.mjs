// Isolated read-only polling regression; all APIs are simulated.
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { mkdir } from 'node:fs/promises'
import assert from 'node:assert/strict'
const root = fileURLToPath(new URL('../../../..', import.meta.url))
const require = createRequire(resolve(root, 'frontend/package.json'))
const { createServer } = require('vite')
const vue = require('@vitejs/plugin-vue').default
const { chromium } = require(process.env.CC_PLAYWRIGHT_PATH || 'playwright')
const server = await createServer({ configFile: false, root: fileURLToPath(new URL('.', import.meta.url)), plugins: [vue()], resolve: { alias: { vue: require.resolve('vue/dist/vue.esm-bundler.js') } }, server: { host: '127.0.0.1', port: 5192, strictPort: true, fs: { allow: [root] } } })
await server.listen()
const browser = await chromium.launch({ headless: true, channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1280, height: 1100 } })
const errors = [], unexpected = []
let polls = 0, ready = false
page.on('pageerror', error => errors.push(error.message))
await page.route('**/*', async route => {
  const url = new URL(route.request().url())
  if (url.hostname !== '127.0.0.1') return route.abort()
  if (url.pathname === '/runtime-config.json') return route.fulfill({ json: { backend_url: url.origin } })
  if (!url.pathname.includes('/api/')) return route.continue()
  const op = url.pathname.split('/').at(-1)
  let result
  if (op === 'list_scan_outcomes') result = { items: [
    { event_id: 'evt_' + '1'.repeat(32), occurred_at: '2026-09-15T09:00:00Z', child_name: 'Synthetic child', status: 'ignored', error_code: 'barsy_credentials_unavailable' },
    { event_id: 'evt_' + '2'.repeat(32), occurred_at: '2026-09-15T09:00:01Z', child_name: null, status: 'unknown_identifier', error_code: null },
  ] }
  else if (op === 'list_operator_accounts') {
    polls++
    result = { items: [{ visit_id: 'visit_' + '3'.repeat(32), child_name: 'Synthetic child', table_name: 'Synthetic room', account_id: 51, admitted: true, live: true, visit_state: 'closed', pending: !ready, error_code: null }], has_more: false }
  } else if (op === 'get_operator_account') result = { choices: [], commands: [{ command_id: 'commercial_' + '4'.repeat(32), kind: 'time', state: ready ? 'confirmed' : 'prepared', article_id: 26, quantity: '0.283', error_code: null }] }
  else { unexpected.push(op); return route.abort() }
  return route.fulfill({ json: result })
})
try {
  await page.goto('http://127.0.0.1:5192/?workflow')
  await page.getByText('Entry denied — check saved Barsy credentials', { exact: true }).waitFor()
  await page.getByText('No attached bracelet with this number', { exact: true }).waitFor()
  await page.locator('.account-list button').click()
  await page.getByText('Queued', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Proceed to payment', exact: true }).isEnabled(), false)
  const output = resolve(root, '.runtime/child-center-0.6.9-review')
  await mkdir(output, { recursive: true })
  await page.screenshot({ path: resolve(output, 'workflow-light.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  await page.screenshot({ path: resolve(output, 'workflow-dark.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(output, 'workflow-mobile.png'), fullPage: true })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  ready = true
  // Without clicking Refresh or re-sending, a pending account updates within 5s.
  await page.waitForFunction(() => {
    const button = Array.from(document.querySelectorAll('button')).find(b => b.textContent === 'Proceed to payment')
    return button && !button.disabled
  }, null, { timeout: 5000 })
  assert.ok(polls >= 3)
  assert.deepEqual(unexpected, [])
  assert.deepEqual(errors, [])
  console.log('Workflow UI: distinct scan failures, pending polling, payment gating, light/dark/mobile passed; no mutations.')
} finally { await browser.close(); await server.close() }
