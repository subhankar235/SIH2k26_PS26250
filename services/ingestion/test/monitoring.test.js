import { test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { EventStore } from '../src/ingestion/store.js';
import { loadConfig } from '../src/platform/config.js';
import { createApp } from '../src/app.js';
import { monitoringSnapshot } from '../src/dashboard/monitoring.js';
import { event } from './fixtures.js';

const NOW = Date.parse('2026-10-15T06:00:00Z');
const ADMIN = 'a'.repeat(48), SOURCE = 's'.repeat(48), VIEWER = 'v'.repeat(48);
async function setup(t, enabled = true) {
  let clock = NOW;
  const config = loadConfig({ INGESTION_ADMIN_TOKEN: ADMIN, INGESTION_SOURCES_JSON: JSON.stringify([
    { sourceId: 'test-source', token: SOURCE, types: ['aircraft.status'] }]), INGESTION_DB_PATH: ':memory:',
    ...(enabled ? { MONITOR_VIEWER_TOKEN: VIEWER } : {}) });
  const store = new EventStore({ path: ':memory:', now: () => clock });
  const app = createApp({ config, store, now: () => clock, publisher: { enabled: false } });
  const server = app.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(async () => { await new Promise((resolve) => server.close(resolve)); store.close(); });
  const origin = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { body, cookie, originHeader = origin, ...options } = {}) => fetch(origin + path, {
    ...options, headers: { ...(body ? { 'Content-Type': 'application/json', Origin: originHeader } : {}),
      ...(cookie ? { Cookie: cookie } : {}), ...options.headers }, body: body ? JSON.stringify(body) : undefined,
  });
  return { store, request, tick: (ms) => { clock += ms; } };
}

test('snapshot preserves source assertions, flags disagreement and time expiry without inference', (t) => {
  let clock = NOW; const store = new EventStore({ path: ':memory:', now: () => clock }); t.after(() => store.close());
  const first = event({ sourceId: 'first', entityId: 'same', data: { status: 'available', airportId: 'HUB', capacityKg: 500 } }, NOW);
  store.acceptBatch([first, event({ sourceId: 'second', entityId: 'same', data: {
    status: 'maintenance', airportId: 'HUB', capacityKg: 500, maintenanceDueAt: new Date(NOW - 1).toISOString(),
  } }, NOW)]);
  let snapshot = monitoringSnapshot(store, {}, clock);
  assert.equal(snapshot.summary.disagreements, 2);
  assert.equal(snapshot.records.find((r) => r.event.sourceId === 'second').reportedStatus, 'maintenance');
  assert.ok(snapshot.records.find((r) => r.event.sourceId === 'second').flags.includes('maintenance_date_passed'));
  assert.equal(snapshot.summary.total, 2);
  assert.equal(monitoringSnapshot(store, { sourceId: 'first' }, clock).summary.disagreements, 0);
  const filtered = monitoringSnapshot(store, { sourceId: 'missing' }, clock);
  assert.equal(filtered.summary.total, 0); assert.equal(filtered.deliveryScope, 'global_outbox');
  assert.equal(filtered.delivery.queued, 2);
  clock += 3600000;
  snapshot = monitoringSnapshot(store, {}, clock);
  assert.equal(snapshot.summary.expired, 2); assert.equal(snapshot.summary.disagreements, 0);
  assert.ok(snapshot.records.every((r) => r.flags.includes('expired')));
});

test('snapshot caps selected facts and explicitly reports truncation and subset counts', (t) => {
  const store = new EventStore({ path: ':memory:', now: () => NOW }); t.after(() => store.close());
  for (let i = 0; i < 1100; i += 100) store.acceptBatch(Array.from({ length: 100 }, (_, j) => event({ entityId: `entity-${i+j}` }, NOW)));
  const snapshot = monitoringSnapshot(store, {}, NOW);
  assert.equal(snapshot.records.length, 1000); assert.equal(snapshot.scope.truncated, true);
  assert.equal(snapshot.summary.total, 1000); assert.equal(snapshot.scope.shown, 1000);
});

test('viewer auth is separate, cookie flags/no-cache are enforced, sessions expire and logout revokes', async (t) => {
  const { store, request, tick } = await setup(t); store.acceptBatch([event({}, NOW)]);
  assert.equal((await request('/monitor/api/snapshot')).status, 401);
  for (const token of [ADMIN, SOURCE, 'bad']) assert.equal((await request('/monitor/session', { method: 'POST', body: { token } })).status, 401);
  const login = await request('/monitor/session', { method: 'POST', body: { token: VIEWER } });
  assert.equal(login.status, 200); const cookie = login.headers.get('set-cookie').split(';')[0];
  assert.match(login.headers.get('set-cookie'), /HttpOnly/); assert.match(login.headers.get('set-cookie'), /SameSite=Strict/);
  assert.match(login.headers.get('cache-control'), /no-store/);
  const snapshot = await request('/monitor/api/snapshot', { cookie }); assert.equal(snapshot.status, 200);
  assert.match(snapshot.headers.get('cache-control'), /no-store/);
  assert.ok(!JSON.stringify(await snapshot.json()).includes(VIEWER));
  assert.equal((await request('/v1/state', { cookie })).status, 401);
  assert.equal((await request('/monitor/api/snapshot?unknown=x', { cookie })).status, 422);
  assert.equal((await request('/monitor/api/snapshot?type=bogus', { cookie })).status, 422);
  assert.equal((await request('/monitor/logout', { method: 'POST', body: {}, cookie })).status, 200);
  assert.equal((await request('/monitor/api/snapshot', { cookie })).status, 401);
  const another = await request('/monitor/session', { method: 'POST', body: { token: VIEWER } });
  const nextCookie = another.headers.get('set-cookie').split(';')[0]; tick(1800000);
  assert.equal((await request('/monitor/api/snapshot', { cookie: nextCookie })).status, 401);
});

test('session mutations require same-origin JSON; disabled viewer stays fail closed', async (t) => {
  const { request } = await setup(t);
  assert.equal((await request('/monitor/session', { method: 'POST', body: { token: VIEWER }, originHeader: 'http://evil.example' })).status, 403);
  assert.equal((await request('/monitor/session', { method: 'POST', body: { token: VIEWER }, originHeader: 'null' })).status, 403);
  assert.equal((await request('/monitor/session', { method: 'POST', body: { token: VIEWER, extra: true } })).status, 422);
  assert.equal((await request('/monitor/session', { method: 'POST', body: { token: 'x'.repeat(10000) } })).status, 413);
  const disabled = await setup(t, false);
  assert.equal((await disabled.request('/monitor/session', { method: 'POST', body: { token: VIEWER } })).status, 503);
});

test('viewer configuration rejects shared credentials and insecure remote origins', () => {
  const env = { INGESTION_ADMIN_TOKEN: ADMIN, INGESTION_SOURCES_JSON: JSON.stringify([
    { sourceId: 'test-source', token: SOURCE, types: ['aircraft.status'] }]) };
  for (const value of [ADMIN, SOURCE, 'short']) assert.throws(() => loadConfig({ ...env, MONITOR_VIEWER_TOKEN: value }));
  assert.throws(() => loadConfig({ ...env, MONITOR_VIEWER_TOKEN: VIEWER, MONITOR_ORIGIN: 'http://remote.example' }));
  assert.throws(() => loadConfig({ ...env, MONITOR_VIEWER_TOKEN: VIEWER, MONITOR_ORIGIN: 'https://remote.example/path' }));
  assert.equal(loadConfig({ ...env, MONITOR_VIEWER_TOKEN: VIEWER, MONITOR_ORIGIN: 'https://remote.example' }).monitor.origin, 'https://remote.example');
});

test('sessions rotate, ambiguous cookies fail closed, and session creation is bounded', async (t) => {
  const { request } = await setup(t);
  const first = await request('/monitor/session', { method: 'POST', body: { token: VIEWER } });
  const oldCookie = first.headers.get('set-cookie').split(';')[0];
  const second = await request('/monitor/session', { method: 'POST', body: { token: VIEWER }, cookie: oldCookie });
  const cookie = second.headers.get('set-cookie').split(';')[0];
  assert.equal((await request('/monitor/api/snapshot', { cookie: oldCookie })).status, 401);
  assert.equal((await request('/monitor/api/snapshot', { cookie: `${cookie}; ${cookie}` })).status, 401);
  for (let i = 1; i < 200; i++) assert.equal((await request('/monitor/session', { method: 'POST', body: { token: VIEWER } })).status, 200);
  const full = await request('/monitor/session', { method: 'POST', body: { token: VIEWER } });
  assert.equal(full.status, 503); assert.equal((await full.json()).error.code, 'SESSION_CAPACITY');
});
