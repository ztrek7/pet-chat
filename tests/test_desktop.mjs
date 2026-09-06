// Node-only regression checks. The SDK/DOM below are explicit test doubles.
// Run: node --experimental-vm-modules --test tests/test_desktop.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'

const source = await readFile(new URL('../desktop/plugin.js', import.meta.url), 'utf8')
const tick = () => new Promise(resolve => setImmediate(resolve))
function atom(initial) {
  let value = initial
  const listeners = new Set()
  return {
    get: () => value,
    set(next) { value = next; for (const fn of listeners) fn(next) },
    listen(fn) { listeners.add(fn); return () => listeners.delete(fn) },
    subscribe(fn) { fn(value); return this.listen(fn) },
    get listeners() { return listeners.size }
  }
}
async function load() {
  const profile = atom('default'), connectionId = atom('local')
  const focusedSessionProfile = atom('default')
  const host = { state: { profile, connectionId, focusedSessionProfile }, notify() {}, navigate() {} }
  const rect = { left: 200, top: 300, bottom: 360, width: 60, height: 60 }
  const pet = { parentElement: null, getBoundingClientRect: () => rect }
  const window = { getComputedStyle: () => ({ position: 'fixed', zIndex: '60', opacity: '1' }) }
  const document = { querySelectorAll: () => [{ parentElement: pet }] }
  const context = vm.createContext({ console, setTimeout, clearTimeout, setInterval, clearInterval, window, document })
  const sdk = { atom, host, useValue: value => value.get(), Button() {}, SegmentedControl() {},
    COMPOSER_AREAS: { middleware: 'middleware' }, PALETTE_AREA: 'palette', ROUTES_AREA: 'routes',
    SIDEBAR_NAV_AREA: 'sidebar', STATUSBAR_AREAS: { right: 'status' } }
  const imports = {
    '@hermes/plugin-sdk': sdk,
    react: { useCallback: fn => fn, useEffect() {}, useState() {}, useRef: value => ({ current: value }) },
    'react/jsx-runtime': { jsx() {}, jsxs() {} }
  }
  const module = new vm.SourceTextModule(source, { context })
  await module.link(name => {
    assert.ok(imports[name], `unsupported import: ${name}`)
    const values = imports[name]
    return new vm.SyntheticModule(Object.keys(values), function () {
      for (const [key, value] of Object.entries(values)) this.setExport(key, value)
    }, { context })
  })
  await module.evaluate()
  const requests = [], disposers = []
  let contributions
  const ctx = {
    registerMany(rows) { contributions = rows; return () => {} },
    onDispose(fn) { disposers.push(fn) },
    storage: { get: () => true, set() {} },
    rest(path, options) {
      return new Promise((resolve, reject) => requests.push({ path, options, resolve, reject }))
    }
  }
  module.namespace.default.register(ctx) // Hermes ignores register's return value.
  const stop = () => disposers.forEach(fn => fn())
  return { api: module.namespace, ctx, requests, profile, connectionId, focusedSessionProfile,
    document, stop, contributions }
}

test('SDK error envelopes keep bounded codes and cost confirmations', async () => {
  const app = await load()
  try {
    assert.equal(app.api.toErrorCode(new Error('409: {"error":"settings_conflict"}')), 'settings_conflict')
    assert.equal(app.api.toErrorCode(new Error('private credentials')), 'backend_unreachable')
    const payload = app.api.errorPayload(new Error('Error invoking remote method: Error: 409: {"error":"confirmation_required","cost_warning":{"warning_id":"test","message":"Confirm cost"}}'))
    assert.equal(payload.cost_warning.warning_id, 'test')
    assert.equal(typeof app.api.errorCopy('constructor'), 'string')
  } finally { app.stop() }
})

test('disable disposes listeners and suppresses late readiness', async () => {
  const app = await load()
  app.stop()
  assert.equal(app.profile.listeners, 0)
  for (const request of app.requests) request.resolve({ state: 'ready' })
  await tick()
  assert.equal(app.api.getReadiness(), 'unknown')
  assert.equal(app.api.beginQuip('hello'), null)
})

test('newest scope wins; sends are unchanged; no off-profile egress', async () => {
  const app = await load()
  try {
    app.profile.set('other')
    app.focusedSessionProfile.set('other')
    const newest = app.requests.at(-1)
    newest.resolve({ state: 'not_configured' })
    await tick()
    for (const request of app.requests.filter(item => item !== newest)) request.resolve({ state: 'ready' })
    await tick()
    assert.equal(app.api.getReadiness(), 'not_configured')
    app.profile.set('default')
    app.focusedSessionProfile.set('default')
    app.requests.at(-1).resolve({ state: 'ready' })
    await tick()
    assert.equal(app.api.getReadiness(), 'ready')
    const draft = { text: 'hello', attachments: ['must not be copied'] }
    const capture = app.contributions.find(row => row.id === 'capture').data.handler
    assert.equal(capture(draft), draft)
    const request = app.requests.at(-1)
    assert.equal(request.path, '/quip')
    assert.deepEqual(Object.keys(request.options.body).sort(), ['prompt', 'request_id'])
    const before = app.requests.length
    app.focusedSessionProfile.set('other')
    assert.equal(capture(draft), draft)
    assert.equal(app.requests.length, before)
    app.focusedSessionProfile.set('default')
    assert.equal(app.api.beginQuip('x'.repeat(4001)), null)
    app.document.querySelectorAll = () => []
    assert.equal(app.api.beginQuip('pet is absent'), null)
    assert.equal(app.requests.length, before)
    app.connectionId.set('remote')
    assert.equal(app.api.getReadiness(), 'unknown')
  } finally { app.stop() }
})
