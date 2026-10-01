// Isolated UI regression. Every API is mocked; no live Barsy or Core writes.
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
const server = await createServer({ configFile: false, root: fileURLToPath(new URL('.', import.meta.url)), plugins: [vue()], resolve: { alias: { vue: require.resolve('vue/dist/vue.esm-bundler.js') } }, server: { host: '127.0.0.1', port: 5193, strictPort: true, fs: { allow: [root] } } })
await server.listen()
const browser = await chromium.launch({ headless: true, channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } })
const errors = [], mutations = [], unexpected = []
let unit = 'hours', articleId = 27, locked = false, reject = false
page.on('pageerror', e => errors.push(e.message))
page.on('dialog', d => d.accept())
await page.route('**/*', async route => {
  const url = new URL(route.request().url())
  if (url.hostname !== '127.0.0.1') return route.abort()
  if (url.pathname === '/runtime-config.json') return route.fulfill({ json: { backend_url: url.origin } })
  if (!url.pathname.includes('/api/')) return route.continue()
  const op = url.pathname.split('/').at(-1)
  let result
  const profile = { article_id: articleId, label: articleId === 28 ? 'Synthetic minute article' : 'Synthetic play article', quantity_precision: unit === 'hours' ? 3 : 0, billing_unit: unit }
  if (op === 'get_timing_configuration') result = { active_mode: 'local_quantity', can_change_active_profile: !locked, local_quantity: profile, barsy_timer: { article_id: null }, local_rounding: 'ceil_total_minute' }
  else if (op === 'get_stay_billing') result = { settings: profile, items: [], has_more: false }
  else if (['list_barsy_parent_links', 'list_consumption_choices'].includes(op)) result = { items: [], has_more: false }
  else if (op === 'discover_consumption_articles') result = { items: [{ article_id: 28, label: 'Synthetic minute article', enabled: false }], has_more: false }
  else if (op === 'set_timing_profile') {
    const body = route.request().postDataJSON()
    assert.ok(body.idempotency_key)
    assert.equal(locked, false)
    mutations.push(body.payload)
    if (reject) result = { status: 'rejected', error_code: 'unit_mismatch' }
    else { unit = body.payload.billing_unit; articleId = body.payload.article_id; result = { status: 'updated' } }
  } else { unexpected.push(op); return route.abort() }
  return route.fulfill({ json: result })
})
try {
  await page.goto('http://127.0.0.1:5193/')
  const select = page.getByLabel('Send time as', { exact: true })
  await select.selectOption('minutes')
  await page.getByText('6 billable minutes → quantity 6. The Barsy price must be per minute.', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Save unit', exact: true }).click()
  await page.getByText('Saved unit: min', { exact: true }).waitFor()
  assert.deepEqual(mutations, [{ mode: 'local_quantity', article_id: 27, billing_unit: 'minutes' }])
  reject = true
  await select.selectOption('hours')
  await page.getByRole('button', { name: 'Save unit', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: 'Unit mismatch.' }).waitFor()
  await page.getByText('Saved unit: min', { exact: true }).waitFor()
  await select.selectOption('minutes')
  reject = false
  await page.getByRole('button', { name: 'Load from Barsy', exact: true }).click()
  await page.getByRole('button', { name: 'Use for time', exact: true }).click()
  await page.getByRole('button', { name: 'Selected', exact: true }).waitFor()
  assert.deepEqual(mutations.at(-1), { mode: 'local_quantity', article_id: 28, billing_unit: 'minutes' })
  const output = resolve(root, '.runtime/child-center-0.7.0-review')
  await mkdir(output, { recursive: true })
  await page.screenshot({ path: resolve(output, 'units-light.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  await page.screenshot({ path: resolve(output, 'units-dark.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.evaluate(() => { localStorage.setItem('preferredLanguage', 'bg'); window.dispatchEvent(new CustomEvent('language-changed', { detail: { language: 'bg' } })) })
  await page.getByLabel('Подаване на времето', { exact: true }).waitFor()
  await page.screenshot({ path: resolve(output, 'units-mobile-bg.png'), fullPage: true })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  locked = true
  await page.reload()
  assert.equal(await page.getByLabel('Подаване на времето', { exact: true }).isDisabled(), true)
  assert.deepEqual(errors, []); assert.deepEqual(unexpected, [])
  console.log('Billing units: saved minutes, explicit payload, locked active visits, EN/BG, light/dark/mobile passed.')
} finally { await browser.close(); await server.close() }
