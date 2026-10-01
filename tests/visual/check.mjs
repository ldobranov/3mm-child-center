// Local-only browser regression; no connection to Raspberry or Barsy.
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { mkdir, readFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const root = fileURLToPath(new URL('../../../..', import.meta.url))
const require = createRequire(resolve(root, 'frontend/package.json'))
const { createServer } = require('vite')
const vue = require('@vitejs/plugin-vue').default
const { chromium } = require(process.env.CC_PLAYWRIGHT_PATH || 'playwright')
const server = await createServer({ configFile: false, root: fileURLToPath(new URL('.', import.meta.url)), plugins: [vue()], resolve: { alias: { vue: require.resolve('vue/dist/vue.esm-bundler.js') } }, server: { host: '127.0.0.1', port: 5189, strictPort: true, fs: { allow: [root] } } })
await server.listen()
const browser = await chromium.launch({ headless: true, channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1400, height: 1200 } })
const errors = []
let acceptDialog = true
page.on('dialog', dialog => acceptDialog ? dialog.accept() : dialog.dismiss())
page.on('pageerror', error => errors.push(error.message))
let enabled = true
let articleId = null
let timedArticleId = null
let accountOpen = true
let commercialRequests = 0
let fiscalRequests = 0
let liveDelivery = false
let braceletAssignments = []
let assignmentRequests = 0
const accessContract = JSON.parse(await readFile(resolve(root, 'modules/child-center/application-extension.json'), 'utf8'))
let staffPermissions = null, accessFailure = false
let operationCalls = []
let previewFailure = false
const previewRequestKeys = []
const registrationId = 'reg_' + '6'.repeat(32), clientChildId = 'child_' + '7'.repeat(32)
const checkoutVisit = 'visit_' + '9'.repeat(32)
let active = [
  { visit_id: checkoutVisit, child_id: 'child_' + '8'.repeat(32), child_display_name: 'Synthetic checkout child', entered_at: new Date().toISOString(), last_event_at: new Date().toISOString(), elapsed_seconds: 740, phase: 'paused', barsy_table: null },
  { visit_id: 'visit_' + 'b'.repeat(32), child_id: 'child_' + 'c'.repeat(32), child_display_name: 'Synthetic paused child', entered_at: new Date().toISOString(), last_event_at: new Date().toISOString(), elapsed_seconds: 740, phase: 'paused', barsy_table: null },
  { visit_id: 'visit_' + 'd'.repeat(32), child_id: 'child_' + 'e'.repeat(32), child_display_name: 'Synthetic playing child', entered_at: new Date().toISOString(), last_event_at: new Date().toISOString(), elapsed_seconds: 1810, phase: 'inside', barsy_table: null },
]
await page.route('**/runtime-config.json', route => route.fulfill({ json: { backend_url: 'http://127.0.0.1:5189' } }))
await page.route('**/api/v1/application-extensions/**', route => {
  let operation = route.request().url().split('/').pop()
  if (operation === 'access') {
    if (accessFailure) return route.fulfill({ status: 503, json: {} })
    return route.fulfill({ json: { module_id: accessContract.module_id, active_version: accessContract.version, user_id: 2, allowed_route_ids: accessContract.routes.filter(r => r.audience === 'operator' && (staffPermissions === null || r.required_permissions.every(p => staffPermissions.has(p)))).map(r => r.route_id), allowed_operation_ids: accessContract.operations.filter(o => o.audiences.includes('operator') && (staffPermissions === null || staffPermissions.has(o.required_permission))).map(o => o.operation_id) } })
  }
  operationCalls.push(operation)
  if (operation === 'get_checkout_account') return route.fulfill({ json: { choices: [], commands: [] } })
  if (operation === 'list_checkout_accounts') operation = 'list_operator_accounts'
  if (operation === 'preview_account_payment') {
    previewRequestKeys.push(route.request().postDataJSON().idempotency_key)
    if (previewFailure) return route.fulfill({ status: 409, json: {} })
  }
  const payload = route.request().postDataJSON()?.payload
  let result
  if (operation === 'get_timing_configuration') result = { active_mode: 'local_quantity', can_change_active_profile: true, local_rounding: 'ceil_total_minute', local_quantity: { article_id: articleId, label: articleId ? 'Synthetic hourly play' : null, quantity_precision: 3 }, barsy_timer: { article_id: timedArticleId, label: timedArticleId ? 'Synthetic timed play' : null, quantity_precision: 3, time_interval: 60, available: false, unavailable_reason: 'stop_api_unverified' } }
  else if (operation === 'set_timing_profile') { if (payload.mode === 'local_quantity') articleId = payload.article_id; else timedArticleId = payload.article_id; result = { status: 'updated' } }
  else if (operation === 'list_barsy_parent_links') result = { items: [{ guardian_id: 'guardian_' + 'a'.repeat(32), display_name: 'Synthetic parent with a long display name', state: 'prepared', remote_client_id: null, error_code: null }], has_more: false }
  else if (operation === 'list_consumption_choices') result = { items: enabled ? [{ code: 'barsy_11', label: 'Synthetic drink with a long article label' }] : [] }
  else if (operation === 'discover_consumption_articles') result = { items: [{ article_id: 11, label: 'Synthetic drink with a long article label', enabled }], has_more: false }
  else if (operation === 'set_consumption_article') { enabled = payload.enabled; result = { status: 'updated' } }
  else if (operation === 'get_stay_billing') result = { settings: { article_id: articleId, label: articleId ? 'Synthetic hourly play' : null, quantity_precision: articleId ? 3 : null }, items: [{ bill_id: 'bill_' + 'f'.repeat(32), visit_id: 'visit_' + 'a'.repeat(32), rounded_minutes: 31, quantity: '0.517', state: 'confirmed', remote_account_id: 501, error_code: null }], has_more: false }
  else if (operation === 'set_stay_article') { articleId = payload.article_id; result = { status: 'updated' } }
  else if (operation === 'get_operator_reader_state') result = { mode: 'automatic_toggle', operator_selected_purpose: 'entry', effective_from: new Date().toISOString() }
  else if (operation === 'list_active_visits') result = { items: active, next_cursor: null }
  else if (operation === 'list_visit_history') result = { items: [{ visit_id: checkoutVisit, child_id: clientChildId, child_display_name: 'Synthetic completed child', guardian_display_name: 'Synthetic parent', entered_at: new Date().toISOString(), exited_at: new Date().toISOString(), duration_seconds: 970, rounded_minutes: 17, entry_source: 'identifier_event', exit_source: 'operator', barsy_table: null }], next_cursor: null }
  else if (operation === 'list_registrations') result = { items: [], next_cursor: null }
  else if (operation === 'list_operator_clients') result = { items: payload.status === 'submitted' || payload.query === 'no match' ? [] : [{ registration_id: registrationId, status: 'approved', guardian_display_name: 'Synthetic regular parent', child_display_names: ['Synthetic regular child'], updated_at: new Date().toISOString() }], next_cursor: null }
  else if (operation === 'get_registration') result = { registration_id: registrationId, status: 'approved', submitted_at: new Date().toISOString(), guardian: { guardian_id: 'guardian_' + '6'.repeat(32), display_name: 'Synthetic regular parent', phone: '', email: 'synthetic@example.invalid' }, children: [{ child_id: clientChildId, display_name: 'Synthetic regular child', allowed_consumption_codes: ['barsy_11'], status: 'active', identifier_assignments: braceletAssignments }] }
  else if (operation === 'assign_identifier') {
    assert.equal(payload.child_id, clientChildId)
    assert.equal(payload.expected_assignment_id, braceletAssignments.find(a => !a.retired_at)?.assignment_id || null)
    assignmentRequests++
    braceletAssignments = [...braceletAssignments.map(a => ({ ...a, retired_at: a.retired_at || new Date().toISOString() })), { assignment_id: 'assign_' + String(assignmentRequests).repeat(32), assigned_at: new Date().toISOString(), retired_at: null, retire_reason: null }]
    result = { status: 'assigned' }
  }
  else if (operation === 'list_stay_bills') result = { items: [{ bill_id: 'bill_' + 'a'.repeat(32), visit_id: 'visit_' + 'b'.repeat(32), child_display_name: 'Synthetic completed child', rounded_minutes: 31, quantity: '0.517', state: 'confirmed', remote_account_id: 501, error_code: null }], has_more: false }
  else if (operation === 'close_visit') { active = active.filter(v => v.visit_id !== payload.visit_id); result = { barsy_table: null } }
  else if (operation === 'list_operator_accounts') result = { items: accountOpen ? [{ visit_id: checkoutVisit, child_name: 'Synthetic checkout child', table_name: 'Synthetic play room', account_id: 502, admitted: true, live: true, visit_state: active.some(v => v.visit_id === checkoutVisit) ? 'active' : 'closed', pending: false, error_code: null }] : [], has_more: false }
  else if (operation === 'get_operator_account') result = { choices: [{ article_id: 11, label: 'Synthetic allowed drink', allowed_for_child: true }, { article_id: 12, label: 'Synthetic parent-only drink', allowed_for_child: false }], commands: [{ command_id: 'commercial_' + '1'.repeat(32), kind: 'time', state: 'confirmed', article_id: 26, quantity: '0.517', consumer: null, error_code: null }] }
  else if (operation === 'add_account_consumption') { assert.equal(payload.consumer, 'child'); assert.equal(payload.article_id, 11); assert.equal(payload.quantity, commercialRequests ? '2' : '1'); commercialRequests++; result = { command_id: 'commercial_' + '2'.repeat(32), state: 'prepared' } }
  else if (operation === 'preview_account_payment') result = { quote_id: 'quote_' + '3'.repeat(32), account_id: 502, amount: '4.20', currency_id: 1, currency_code: 'EUR', expires_at: new Date(Date.now() + 120000).toISOString(), methods: [{ paymethod_id: 1, label: 'Synthetic cash', type_id: 1 }, { paymethod_id: 2, label: 'Synthetic card', type_id: 5 }] }
  else if (operation === 'pay_account') { assert.equal(payload.confirmed, true); assert.equal(payload.paymethod_id, 1); fiscalRequests++; accountOpen = false; result = { command_id: 'commercial_' + '4'.repeat(32), state: 'prepared' } }
  else if (operation === 'list_clients') result = { items: [], next_cursor: null }
  else if (operation === 'secrets') result = { items: [] }
  else if (operation === 'operational-status') result = { connectors: { items: [{ connector_id: 'barsy_api', enabled: true, destination_origin: 'https://synthetic.example.invalid', last_outcome: 'succeeded', last_http_status: 200 }] } }
  else if (operation === 'list_barsy_table_pool') result = { items: [], configured: 0, enabled: 0, free: 0, allocated: 0, delivery_mode: liveDelivery ? 'live_start' : 'mock' }
  else if (operation === 'get_barsy_integration_status') result = { production_mutations_enabled: liveDelivery, commands: [], start_commands: 0, stop_commands: 0, ambiguous: 0, manual_review: 0 }
  else if (operation === 'set_barsy_delivery_mode') { liveDelivery = payload.enabled; result = { status: 'updated' } }
  else throw new Error('Unexpected preview operation: ' + operation)
  return route.fulfill({ json: result })
})
const output = resolve(root, '.runtime/child-center-daily-review')
await mkdir(output, { recursive: true })
try {
  await page.goto('http://127.0.0.1:5189/?admin')
  await page.getByRole('button', { name: 'Barsy Connection and tables', exact: true }).click()
  await page.getByText('Test mode — nothing is sent to Barsy', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Active', exact: true }).count(), 0)
  assert.equal(await page.getByLabel('Parent’s Barsy client ID').isVisible(), false)
  await page.getByRole('button', { name: 'Troubleshooting', exact: true }).click()
  await page.getByText('Waiting for live delivery', { exact: true }).waitFor()
  await page.getByText('Resolve a problem', { exact: true }).click()
  await page.getByLabel('Parent’s Barsy client ID').waitFor()
  await page.screenshot({ path: resolve(output, 'review.png'), fullPage: true })
  await page.getByRole('button', { name: 'Setup', exact: true }).click()
  await page.getByRole('button', { name: 'Enable live delivery', exact: true }).click()
  assert.equal(liveDelivery, true)
  await page.getByText('Live delivery', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Load from Barsy', exact: true }).click()
  await page.getByRole('button', { name: 'Use for time', exact: true }).click()
  await page.getByRole('button', { name: 'Selected', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Activation unavailable', exact: true }).count(), 0)
  await page.getByText('Barsy timer — future capability', { exact: true }).click()
  await page.getByLabel('Configure article for:', { exact: true }).selectOption('barsy_timer')
  await page.getByRole('button', { name: 'Use for time', exact: true }).click()
  await page.getByText('Synthetic timed play', { exact: true }).waitFor()
  assert.equal(articleId, 11)
  assert.equal(timedArticleId, 11)
  await page.getByLabel('Configure article for:', { exact: true }).selectOption('local_quantity')
  await page.getByText('Barsy timer — future capability', { exact: true }).click()
  await page.screenshot({ path: resolve(output, 'light.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  await page.screenshot({ path: resolve(output, 'dark.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(output, 'mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Page must not overflow horizontally')
  await page.getByRole('checkbox', { name: 'Synthetic drink with a long article label', exact: true }).first().uncheck()
  await page.getByText('No articles selected.', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Tables', exact: true }).click()
  await page.getByRole('heading', { name: 'Child Center tables', exact: true }).waitFor()
  await page.screenshot({ path: resolve(output, 'tables-mobile.png'), fullPage: true })
  await page.goto('http://127.0.0.1:5189/?operator')
  await page.getByRole('button', { name: /Synthetic regular parent/ }).click()
  await page.getByRole('button', { name: 'Give bracelet', exact: true }).click()
  await page.getByLabel('Bracelet code', { exact: true }).fill('synthetic-daily-keyboard')
  await page.getByLabel('Bracelet code', { exact: true }).press('Enter')
  await page.getByText('Bracelet assigned. Ready to scan at the entrance.', { exact: true }).waitFor()
  assert.equal(assignmentRequests, 1)
  assert.equal(active.length, 3, 'Assigning a bracelet must not record entry')
  await page.getByRole('button', { name: 'Replace bracelet', exact: true }).click()
  await page.getByLabel('Bracelet code', { exact: true }).fill('synthetic-replacement')
  await page.getByLabel('Bracelet code', { exact: true }).press('Enter')
  await page.getByText('Bracelet assigned. Ready to scan at the entrance.', { exact: true }).waitFor()
  assert.equal(assignmentRequests, 2)
  await page.screenshot({ path: resolve(output, 'clients-mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Client desk must not overflow')
  await page.setViewportSize({ width: 1400, height: 1000 })
  await page.screenshot({ path: resolve(output, 'clients-light.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.classList.add('dark', 'dark-mode'))
  await page.screenshot({ path: resolve(output, 'clients-dark.png'), fullPage: true })
  await page.getByLabel('Find a client', { exact: true }).fill('no match')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByText('No registrations match this filter.', { exact: true }).waitFor()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'In the play area', exact: true }).click()
  await page.getByText('Paused — outside', { exact: true }).waitFor()
  await page.screenshot({ path: resolve(output, 'visits-mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Visits page must not overflow')
  assert(await page.evaluate(() => Array.from(document.querySelectorAll('.cc-visit')).every(e => e.getBoundingClientRect().right <= e.closest('.cc-panel').getBoundingClientRect().right)), 'Visit cards must not be clipped')
  await page.setViewportSize({ width: 1400, height: 1000 })
  await page.evaluate(() => document.documentElement.classList.add('dark', 'dark-mode'))
  await page.screenshot({ path: resolve(output, 'visits-dark.png'), fullPage: true })
  await page.getByRole('button', { name: 'Finish and send to Barsy', exact: true }).first().click()
  await page.getByText('Playing finished. Time recorded and bracelet released. Proceed to payment.', { exact: true }).waitFor()
  assert.equal(await page.locator('.cc-visit').count(), 1)
  await page.getByText('Previous workflow reports', { exact: true }).click()
  await page.getByText('Confirmed in Barsy', { exact: true }).waitFor()
  await page.getByText('Previous workflow reports', { exact: true }).click()
  await page.getByRole('button', { name: /Synthetic checkout child/ }).click()
  await page.getByLabel('Search this page', { exact: true }).fill('no match')
  await page.getByText('No matches on this page.', { exact: true }).waitFor()
  await page.getByLabel('Search this page', { exact: true }).fill('')
  await page.screenshot({ path: resolve(output, 'playing-dark.png'), fullPage: true })
  await page.getByRole('button', { name: '+1 · Synthetic allowed drink', exact: true }).click()
  await page.getByText('Request recorded. Check its status below.', { exact: true }).waitFor()
  assert.equal(commercialRequests, 1)
  await page.locator('.consumption select').nth(1).selectOption('11')
  await page.locator('.consumption input').fill('2')
  assert.equal(await page.locator('.consumption select').nth(1).locator('option').count(), 2)
  await page.getByRole('button', { name: 'Add to account', exact: true }).click()
  await page.getByText('Request recorded. Check its status below.', { exact: true }).waitFor()
  assert.equal(commercialRequests, 2)
  await page.getByRole('button', { name: 'Finish playing', exact: true }).click()
  await page.getByRole('button', { name: 'Proceed to payment', exact: true }).waitFor()
  assert(await page.getByRole('button', { name: 'Awaiting payment', exact: true }).evaluate(e => e.classList.contains('cc-button--primary')), 'Finishing moves to the payment queue')
  assert(await page.getByRole('heading', { name: /Synthetic checkout child/ }).isVisible(), 'Selection survives finishing')
  await page.getByRole('button', { name: 'Proceed to payment', exact: true }).click()
  assert(await page.getByRole('button', { name: 'Pay and close account', exact: true }).isDisabled())
  await page.locator('.payment select').selectOption('1')
  assert.equal(await page.locator('.payment input[type=checkbox]').count(), 0)
  assert(await page.getByRole('button', { name: 'Pay and close account', exact: true }).isEnabled())
  acceptDialog = false
  await page.getByRole('button', { name: 'Pay and close account', exact: true }).click()
  assert.equal(fiscalRequests, 0, 'Dismissing confirmation must not submit payment')
  acceptDialog = true
  await page.screenshot({ path: resolve(output, 'checkout-dark.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.classList.remove('dark', 'dark-mode'))
  await page.screenshot({ path: resolve(output, 'checkout-light.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(output, 'checkout-mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Checkout must not overflow horizontally')
  await page.getByRole('button', { name: 'Pay and close account', exact: true }).click()
  await page.getByText('No open accounts in the new workflow.', { exact: true }).waitFor()
  assert.equal(fiscalRequests, 1)
  await page.getByRole('button', { name: 'Approved clients', exact: true }).click()
  await page.getByRole('button', { name: 'New client and bracelet', exact: true }).click()
  await page.getByRole('button', { name: 'Register client and bracelet', exact: true }).waitFor()
  await page.goto('http://127.0.0.1:5189/?history')
  await page.getByText('Billable: 17 min', { exact: true }).waitFor()
  await page.getByText('00:16:10', { exact: true }).waitFor()
  await page.screenshot({ path: resolve(output, 'history-mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'History must not overflow')
  await page.setViewportSize({ width: 1400, height: 1000 })
  await page.screenshot({ path: resolve(output, 'history-light.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.classList.add('dark', 'dark-mode'))
  await page.screenshot({ path: resolve(output, 'history-dark.png'), fullPage: true })
  staffPermissions = new Set(['registrations_manage', 'children_manage'])
  operationCalls = []
  await page.goto('http://127.0.0.1:5189/?operator')
  await page.getByRole('button', { name: /Synthetic regular parent/ }).click()
  await page.getByRole('button', { name: 'Replace bracelet', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'In the play area', exact: true }).count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Awaiting payment', exact: true }).count(), 0)
  assert(!operationCalls.includes('list_active_visits') && !operationCalls.includes('list_operator_accounts'), 'Reception must not load forbidden hidden data')
  await page.screenshot({ path: resolve(output, 'reception-access.png'), fullPage: true })
  staffPermissions = new Set()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByText('You do not have access to this screen. Contact an administrator.', { exact: true }).waitFor()
  assert.equal(await page.getByText('Synthetic regular parent', { exact: true }).count(), 0, 'Revocation clears personal data')
  accessFailure = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByText('Access could not be verified. Check your login and connection.', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'New client and bracelet', exact: true }).count(), 0)
  accessFailure = false; staffPermissions = new Set(['visits_manage']); accountOpen = true
  await page.goto('http://127.0.0.1:5189/?visits')
  await page.getByRole('button', { name: /Synthetic checkout child/ }).click()
  await page.getByRole('heading', { name: /Synthetic checkout child/ }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Approved clients', exact: true }).count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Proceed to payment', exact: true }).count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Verify an account already paid in Barsy', exact: true }).count(), 0)
  await page.screenshot({ path: resolve(output, 'operator-no-payments.png'), fullPage: true })
  await page.goto('http://127.0.0.1:5189/?history')
  await page.getByText('Synthetic completed child', { exact: true }).waitFor()
  staffPermissions = new Set(['registrations_manage', 'children_manage'])
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByText('You do not have access to this screen. Contact an administrator.', { exact: true }).waitFor()
  assert.equal(await page.getByText('Synthetic completed child', { exact: true }).count(), 0, 'History revocation clears loaded data')
  operationCalls = []
  await page.reload()
  await page.getByText('You do not have access to this screen. Contact an administrator.', { exact: true }).waitFor()
  assert(!operationCalls.includes('list_visit_history'), 'Denied history must not query personal data')

  const pendingKey = 'synthetic-uncertain-preview'
  const savedAttempt = { signature: JSON.stringify(['preview_account_payment', { visit_id: checkoutVisit }]), key: pendingKey }
  const blockedMessage = 'An unconfirmed action belongs to a previous session or requires missing permissions. Do not repeat it; the responsible staff member must review it.'
  // Unknown owner, different owner, and revoked payment permission cannot replay.
  for (const [owner, payments] of [[undefined, true], [3, true], [2, false]]) {
    staffPermissions = new Set(['visits_manage', ...(payments ? ['payments_manage'] : [])])
    await page.evaluate(attempt => sessionStorage.setItem('childCenterCommercialAttemptV1', JSON.stringify(attempt)), { ...savedAttempt, userId: owner })
    const previousPreviews = previewRequestKeys.length
    await page.goto('http://127.0.0.1:5189/?visits')
    await page.getByText(blockedMessage, { exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Recover the previous action result', exact: true }).count(), 0)
    assert.equal(previewRequestKeys.length, previousPreviews, 'Blocked attempts never replay automatically')
    assert.equal(await page.evaluate(() => JSON.parse(sessionStorage.getItem('childCenterCommercialAttemptV1')).key), pendingKey)
  }
  // Same owner recovers only explicitly and keeps the key after a rejected retry.
  staffPermissions = new Set(['visits_manage', 'payments_manage'])
  await page.reload()
  previewFailure = true
  await page.getByRole('button', { name: 'Recover the previous action result', exact: true }).click()
  await page.getByText('The data has changed or is invalid.', { exact: true }).waitFor()
  assert.equal(previewRequestKeys.at(-1), pendingKey)
  assert.equal(await page.evaluate(() => JSON.parse(sessionStorage.getItem('childCenterCommercialAttemptV1')).key), pendingKey, 'A recovery rejection must not discard the original identity')
  previewFailure = false
  await page.getByRole('button', { name: 'Recover the previous action result', exact: true }).click()
  await page.getByText('The previous result was recovered using the same request identity.', { exact: true }).waitFor()
  assert.equal(previewRequestKeys.at(-1), pendingKey)
  assert.equal(await page.evaluate(() => sessionStorage.getItem('childCenterCommercialAttemptV1')), null)
  assert.equal(fiscalRequests, 1, 'Recovering a preview must not send payment')
  staffPermissions = new Set(['payments_manage'])
  operationCalls = []
  await page.goto('http://127.0.0.1:5189/?cashier')
  await page.getByRole('heading', { name: 'Checkout', exact: true }).waitFor()
  await page.getByRole('button', { name: /Synthetic checkout child/ }).click()
  assert.equal(await page.locator('.consumption, .quick-consumption').count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Finish playing', exact: true }).count(), 0)
  assert(!operationCalls.some(op => ['list_active_visits', 'list_operator_accounts', 'get_operator_account', 'list_operator_clients'].includes(op)), 'Cashier never calls visit or registration reads')
  await page.getByRole('button', { name: 'Proceed to payment', exact: true }).click()
  await page.locator('.payment select').selectOption('1')
  assert.equal(await page.locator('.payment input[type=checkbox]').count(), 0)
  await page.screenshot({ path: resolve(output, 'cashier-light.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.classList.add('dark', 'dark-mode'))
  await page.screenshot({ path: resolve(output, 'cashier-dark.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(output, 'cashier-mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Cashier must not overflow')
  await page.getByRole('button', { name: 'Pay and close account', exact: true }).click()
  await page.getByText('No open accounts in the new workflow.', { exact: true }).waitFor()
  assert.equal(fiscalRequests, 2)
  staffPermissions = new Set()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByText('You do not have access to this screen. Contact an administrator.', { exact: true }).waitFor()
  assert.deepEqual(errors, [])
  console.log('Visual and article-toggle checks passed:', output)
} finally { await browser.close(); await server.close() }
