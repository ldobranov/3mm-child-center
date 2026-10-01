// Isolated browser regression. All API calls are intercepted; no real devices/POS.
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
const server = await createServer({ configFile: false, root: fileURLToPath(new URL('.', import.meta.url)), plugins: [vue()], resolve: { alias: { vue: require.resolve('vue/dist/vue.esm-bundler.js') } }, server: { host: '127.0.0.1', port: 5191, strictPort: true, fs: { allow: [root] } } })
await server.listen()
const browser = await chromium.launch({ headless: true, channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1280, height: 1100 } })
const errors = [], mutations = []
page.on('pageerror', e => errors.push(e.message))
let granted = true, completed = false, abortFirst = true
const output = resolve(root, '.runtime/child-center-0.6.8-review')
await mkdir(output, { recursive: true })
await page.route('**/*', async route => {
  const url = new URL(route.request().url())
  if (url.hostname !== '127.0.0.1') return route.abort()
  if (url.pathname === '/runtime-config.json') return route.fulfill({ json: { backend_url: url.origin } })
  if (!url.pathname.includes('/api/')) return route.continue()
  if (url.pathname.endsWith('/access')) return route.fulfill({ json: {
    module_id: 'org.3mm.child-center', active_version: '0.6.8', user_id: 91,
    allowed_route_ids: granted ? ['access_settings'] : [], allowed_operation_ids: granted ? ['get_access_status', 'get_access_settings', 'configure_access_point', 'resolve_unsent_access', 'reconcile_access'] : [],
  } })
  const operation = url.pathname.split('/').at(-1)
  if (operation === 'get_access_settings') return route.fulfill({ json: {
    point_id: 'point_' + '1'.repeat(32), enabled: true, binding_valid: true,
    reader_id: 'reader.synthetic', channel: 'gpio.output.1', duration_ms: 100,
    sensor_id: 'access.sensor', reader_device: 'dev_' + '1'.repeat(32),
    output_device: 'dev_' + '2'.repeat(32), sensor_device: 'dev_' + '2'.repeat(32),
  } })
  if (operation === 'get_access_status') return route.fulfill({ json: {
    enabled: true, binding_valid: true, has_more: false, items: completed ? [] : [{
      request_id: 'access_' + '3'.repeat(32), visit_id: 'visit_' + '4'.repeat(32),
      state: 'review', error_code: 'submit_outcome_unknown', inside_since: null,
      expires_at: '2026-01-01T00:00:00Z', child_name: 'Synthetic child with a deliberately long display name',
    }],
  } })
  if (operation === 'reconcile_access') {
    mutations.push(route.request().postDataJSON())
    if (abortFirst) { abortFirst = false; return route.abort() }
    completed = true
    return route.fulfill({ json: { request_id: 'access_' + '3'.repeat(32), state: 'resolved' } })
  }
  throw new Error('Unexpected API call: ' + operation)
})
try {
  await page.goto('http://127.0.0.1:5191/?access')
  await page.getByRole('button', { name: 'Manual review', exact: true }).waitFor()
  await page.screenshot({ path: resolve(output, 'access-light.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  await page.screenshot({ path: resolve(output, 'access-dark.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(output, 'access-mobile.png'), fullPage: true })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await page.getByRole('button', { name: 'Manual review', exact: true }).click()
  assert.equal(await page.getByRole('button', { name: 'Record review', exact: true }).isEnabled(), false)
  await page.getByLabel('The device is physically isolated; no movement is pending.').check()
  await page.getByLabel('I verified the location and accept correction at the current time.').check()
  await page.getByRole('button', { name: 'Record review', exact: true }).click()
  await page.getByRole('button', { name: 'Retry the same request', exact: true }).click()
  await page.getByText('No pending passages.', { exact: true }).waitFor()
  assert.equal(mutations.length, 2)
  assert.equal(mutations[0].idempotency_key, mutations[1].idempotency_key)
  assert.deepEqual(mutations[0].payload, mutations[1].payload)
  granted = false
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByText('You do not have access to this screen. Contact an administrator.', { exact: true }).waitFor()
  assert.equal(await page.getByRole('heading', { name: 'Access points', exact: true }).count(), 0)
  assert.deepEqual(errors, [])
  console.log('Access UI: light/dark/mobile, explicit review, stable retry identity and access revocation passed.')
} finally { await browser.close(); await server.close() }
