// Diagnostic-only UI regression. Every API response is synthetic; no POS writes.
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
const server = await createServer({ configFile: false, root: fileURLToPath(new URL('.', import.meta.url)), plugins: [vue()], resolve: { alias: { vue: require.resolve('vue/dist/vue.esm-bundler.js') } }, server: { host: '127.0.0.1', port: 5194, strictPort: true, fs: { allow: [root] } } })
await server.listen()
const browser = await chromium.launch({ headless: true, channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1280, height: 1100 } })
const errors = [], unexpected = []
let admissionCode = 'barsy_place_timing_enabled', admitted = false, commands = []
let observation = { status: 'unknown', checked_at: null, error_code: null }
let released = false, releasePath = ''
page.on('pageerror', error => errors.push(error.message))
page.on('dialog', dialog => { void dialog.accept() })
await page.route('**/*', async route => {
  const url = new URL(route.request().url())
  if (url.hostname !== '127.0.0.1') return route.abort()
  if (url.pathname === '/runtime-config.json') return route.fulfill({ json: { backend_url: url.origin } })
  if (!url.pathname.includes('/api/')) return route.continue()
  const op = url.pathname.split('/').at(-1)
  let result
  if (op === 'list_scan_outcomes') result = { items: ['no_enabled_tables', 'no_free_tables'].map((code, index) => ({ event_id: 'evt_' + String(index + 1).repeat(32), occurred_at: '2026-09-16T09:00:00Z', child_name: 'Synthetic child', status: 'ignored', error_code: code })) }
  else if (op === 'list_operator_accounts') result = { items: released ? [] : [{ visit_id: 'visit_' + '3'.repeat(32), child_name: 'Synthetic child', table_name: 'Synthetic room', account_id: 51, admitted, live: true, visit_state: admitted ? 'closed' : 'active', pending: commands.some(c => c.state === 'ambiguous'), error_code: admissionCode, remote_observation: observation }], has_more: false }
  else if (op === 'get_operator_account') result = { choices: [{ article_id: 18, label: 'Synthetic drink', allowed_for_child: true }], commands }
  else if (op === 'reconcile_account_command') { commands = commands.map(c => ({ ...c, state: 'failed', error_code: 'operator_verified_absent_in_barsy' })); result = { status: 'retry_available' } }
  else if (op === 'release_incomplete_closed_account') {
    releasePath = url.pathname
    if (!url.pathname.endsWith('/org.3mm.child-center/operations/release_incomplete_closed_account')) return route.fulfill({ status: 403, json: { detail: 'Administrator route required' } })
    released = true; result = { status: 'released_incomplete' }
  }
  else { unexpected.push(op); return route.abort() }
  return route.fulfill({ json: result })
})
async function refresh() {
  const reply = page.waitForResponse(response => response.url().endsWith('/get_operator_account'))
  await page.getByRole('button', { name: /^(Refresh accounts|Обнови сметките)$/ }).click()
  await reply
  await page.locator('.account-desk > header button:not(:disabled)').waitFor()
}
async function language(value) { await page.evaluate(value => window.dispatchEvent(new CustomEvent('language-changed', { detail: { language: value } })), value) }
function command(kind, code = 'barsy_http_501') {
  return { command_id: 'commercial_' + '4'.repeat(32), kind, state: 'ambiguous', article_id: kind === 'payment' ? null : 28, quantity: kind === 'payment' ? null : '93.000', billing_unit: kind === 'time' ? 'minutes' : null, error_code: code }
}
try {
  await page.goto('http://127.0.0.1:5194/?workflow')
  await page.getByText('Entry denied — an administrator must enable at least one table in Administration → Barsy → Tables', { exact: true }).waitFor()
  await page.getByText('Entry denied — no enabled table is free. Check open accounts in Barsy', { exact: true }).waitFor()
  await page.locator('.account-list button').click()
  for (const [code, expected] of [
    ['barsy_place_timing_enabled', 'The Barsy place type has automatic timing enabled.'],
    ['barsy_place_timing_unknown', 'Automatic timing for the Barsy place could not be verified.'],
    ['barsy_order_timer_active', 'An obsolete check of an unreliable flag blocked confirmation.'],
    ['barsy_orders_invalid', 'Barsy did not return a valid account row list.'],
    ['account_requires_review', 'The account has not passed the billing safety check.'],
  ]) {
    admissionCode = code; await refresh()
    await page.locator('.account-detail p[role="status"]').filter({ hasText: expected }).waitFor()
    assert.equal(await page.getByText('Wait for account confirmation before admitting the child.', { exact: true }).count(), 0)
    assert.equal(await page.getByRole('button', { name: 'Add to account', exact: true }).isEnabled(), false)
  }
  admissionCode = null; await refresh()
  await page.getByText('The account is open. An automatic Barsy check is pending before the child can be admitted.', { exact: true }).waitFor()
  admitted = true; commands = [command('time')]; await refresh()
  const diagnostic = page.locator('.commands article p.error')
  await diagnostic.filter({ hasText: 'Barsy returned HTTP 501.' }).waitFor()
  assert.match(await diagnostic.innerText(), /Adding the article is unconfirmed/)
  assert.doesNotMatch(await diagnostic.innerText(), /fiscal|not sent|rejected/i)
  assert.equal(await page.getByRole('button', { name: 'Retry unsent request', exact: true }).count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Proceed to payment', exact: true }).isEnabled(), false)
  await page.getByRole('button', { name: 'Check rows in Barsy', exact: true }).click()
  await page.getByText('Barsy does not contain this row.', { exact: false }).waitFor()
  await page.getByRole('button', { name: 'Retry unsent request', exact: true }).waitFor()
  commands = [command('consumption')]; await refresh()
  assert.doesNotMatch(await diagnostic.innerText(), /fiscal/i)
  commands = [command('payment')]; await refresh()
  await diagnostic.filter({ hasText: 'fiscal device' }).waitFor()
  assert.match(await diagnostic.innerText(), /do not pay again/)
  commands = [command('time', 'barsy_http_501_RAW_SECRET')]; await refresh()
  assert.doesNotMatch(await diagnostic.innerText(), /RAW_SECRET|HTTP 501/)
  commands = [{ ...command('time', 'barsy_article_price_missing'), state: 'failed' }]; await refresh()
  await page.locator('.commands article p').filter({ hasText: 'incorrect preflight check' }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Proceed to payment', exact: true }).isEnabled(), false)
  await page.getByText('Playing time and consumption must be sent before payment.', { exact: false }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Retry unsent request', exact: true }).count(), 1)
  await language('bg')
  await page.locator('.commands article p').filter({ hasText: 'грешна предварителна проверка' }).waitFor()
  commands = [{ ...command('time'), state: 'confirmed', error_code: null }]; await refresh()
  assert.equal(await page.getByRole('button', { name: 'Към плащане', exact: true }).isEnabled(), true)
  commands = [command('time')]; await refresh(); await language('bg')
  await diagnostic.filter({ hasText: 'Barsy върна HTTP 501.' }).waitFor()
  assert.match(await diagnostic.innerText(), /Добавянето на артикула не е потвърдено/)
  assert.doesNotMatch(await diagnostic.innerText(), /фискал/)
  await page.getByText('Входът е отказан — администраторът трябва да включи поне една маса в Администрация → Barsy → Маси', { exact: true }).waitFor()
  // External closure appears through read-only polling, without an operator refresh.
  commands = []
  observation = { status: 'closed', checked_at: '2026-09-22T07:00:00Z', error_code: 'closed_external_review' }
  await page.locator('.external-closure').waitFor({ timeout: 15000 })
  assert.match(await page.locator('.stay-summary').innerText(), /Затворена в Barsy — нужна проверка/)
  assert.equal(await page.getByRole('button', { name: 'Към плащане', exact: true }).count(), 0)
  assert.equal(await page.getByRole('button', { name: '+1 · Synthetic drink', exact: true }).isEnabled(), false)
  await page.getByRole('button', { name: 'Провери вече платена сметка в Barsy', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Освободи непълната затворена сметка', exact: true }).waitFor()
  await language('en')
  await page.locator('.external-closure').filter({ hasText: 'does not confirm' }).waitFor()
  assert.match(await page.locator('.stay-summary').innerText(), /Closed in Barsy — review required/)
  await language('bg')
  await page.getByRole('button', { name: 'Освободи непълната затворена сметка', exact: true }).click()
  await page.getByText('Масата е освободена. Сметката не е отбелязана като напълно начислена или платена.', { exact: true }).waitFor()
  assert.match(releasePath, /\/org\.3mm\.child-center\/operations\/release_incomplete_closed_account$/)
  assert.equal(await page.locator('.account-list button').count(), 0)
  const output = resolve(root, '.runtime/child-center-diagnostics-review')
  await mkdir(output, { recursive: true })
  await page.screenshot({ path: resolve(output, 'diagnostics-light-bg.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(output, 'diagnostics-dark-mobile-bg.png'), fullPage: true })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  assert.deepEqual(unexpected, [])
  assert.deepEqual(errors, [])
  console.log('Diagnostics UI passed: admission causes, disabled/full tables, HTTP501, missing sale price, external closure polling and blocked actions, BG/EN and mobile; no mutations.')
} finally { await browser.close(); await server.close() }
