import { test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { EventStore } from '../src/store.js';
import { event } from './fixtures.js';

const NOW = Date.parse('2026-10-15T06:00:00Z');
const ADMIN = 'test-admin-'.padEnd(48, 'A'); const SOURCE = 'test-source-'.padEnd(48, 'B');
async function setup(t, overrides = {}, publisher = { enabled: false, flush: async () => ({ enabled: false, published: 0 }) }) {
  const config = loadConfig({ INGESTION_ADMIN_TOKEN: ADMIN, INGESTION_SOURCES_JSON: JSON.stringify([
    { sourceId: 'test-source', token: SOURCE, types: ['aircraft.status'] },
  ]), INGESTION_DB_PATH: ':memory:', ...overrides });
  const store = new EventStore({ path: ':memory:', now: () => NOW, maxPending: config.maxPending });
  const app = createApp({ config, store, publisher, now: () => NOW, logger: () => {} });
  const server = app.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(async () => { await new Promise((resolve) => server.close(resolve)); store.close(); });
  const url = `http://127.0.0.1:${server.address().port}`;
  return { store, app, send: async (path, { token = ADMIN, method = 'GET', body, headers = {} } = {}) => {
    const response = await fetch(url + path, { method, headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...headers },
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined });
    return { status: response.status, headers: response.headers, body: await response.json() };
  } };
}
function input(overrides = {}) { return event({ sourceId: 'test-source', ...overrides }, NOW); }
test('health is minimal and every admin route requires the separate admin credential', async (t) => {
  const { send } = await setup(t);
  assert.deepEqual((await send('/health/live', { token: null })).body, { status: 'ok' });
  for (const path of ['/v1/events', '/v1/state', '/v1/outbox', '/v1/metrics', '/v1/schema']) {
    assert.equal((await send(path, { token: null })).status, 401);
    assert.equal((await send(path, { token: SOURCE })).status, 401);
  }
});
test('a valid request persists and retries without claiming Kafka delivery', async (t) => {
  const { send } = await setup(t); const body = input();
  const first = await send('/v1/events', { token: SOURCE, method: 'POST', body });
  assert.equal(first.status, 201); assert.equal(first.body.delivery, 'queued');
  const retry = await send('/v1/events', { token: SOURCE, method: 'POST', body });
  assert.equal(retry.status, 200); assert.equal(retry.body.cursor, first.body.cursor); assert.equal(retry.body.duplicate, true);
  const history = await send(`/v1/events/${body.eventId}`);
  assert.equal(history.body.event.eventId, body.eventId);
});
test('spoofed source and wrong type are forbidden and unknown data fields rejected', async (t) => {
  const { send, store } = await setup(t);
  assert.equal((await send('/v1/events', { token: SOURCE, method: 'POST', body: input({ sourceId: 'another-source' }) })).status, 403);
  assert.equal((await send('/v1/events', { token: SOURCE, method: 'POST', body: input({ type: 'weather.observation' }) })).status, 403);
  assert.equal((await send('/v1/events', { token: SOURCE, method: 'POST', body: input({ privateNotes: 'sensitive' }) })).status, 422);
  assert.equal(store.metrics().events, 0);
});
test('batch conflicts are atomic and structured error contracts include request IDs', async (t) => {
  const { send, store } = await setup(t); const existing = input();
  await send('/v1/events', { token: SOURCE, method: 'POST', body: existing });
  const response = await send('/v1/events/batch', { token: SOURCE, method: 'POST',
    body: { events: [input({ sequence: 2 }), { ...existing, sequence: 3 }] } });
  assert.equal(response.status, 409); assert.equal(response.body.error.code, 'EVENT_ID_CONFLICT');
  assert.equal(response.body.requestId, response.headers.get('x-request-id'));
  assert.equal(store.metrics().events, 1);
});
test('parser errors, unsupported content, body caps, and unknown routes share error semantics', async (t) => {
  const { send } = await setup(t);
  assert.equal((await send('/v1/events', { token: SOURCE, method: 'POST', body: '{broken' })).status, 400);
  assert.equal((await send('/v1/events', { token: SOURCE, method: 'POST', body: '{}', headers: { 'Content-Type': 'text/plain' } })).status, 415);
  assert.equal((await send('/v1/events', { token: SOURCE, method: 'POST', body: JSON.stringify({ huge: 'a'.repeat(270000) }) })).status, 413);
  const missing = await send('/v1/does-not-exist');
  assert.equal(missing.status, 404); assert.equal(missing.body.error.code, 'NOT_FOUND');
  assert.ok(!JSON.stringify(missing.body).includes('stack'));
});
test('all paginated endpoints reject unknown or malformed query parameters', async (t) => {
  const { send } = await setup(t);
  for (const path of ['/v1/events?limit=101', '/v1/state?after=-1', '/v1/outbox?status=invalid',
    '/v1/events?limit=1&limit=2', '/v1/events?unknown=yes', '/v1/events?after=9007199254740992']) {
    assert.equal((await send(path)).status, 422, path);
  }
});
test('admin can retrieve generated schemas, freshness, metrics, and historical pagination', async (t) => {
  const { send } = await setup(t);
  await send('/v1/events', { token: SOURCE, method: 'POST', body: input() });
  await send('/v1/events', { token: SOURCE, method: 'POST', body: input({ sequence: 2 }) });
  const history = await send('/v1/events?limit=1'); assert.equal(history.body.items.length, 1);
  assert.ok(history.body.nextCursor > 0);
  assert.equal((await send('/v1/state')).body.items[0].freshness, 'current');
  assert.equal((await send('/v1/schema')).body.schemas['aircraft.status'].type, 'object');
  const metrics = await send('/v1/metrics'); assert.equal(metrics.body.store.events, 2);
  assert.ok(!JSON.stringify(metrics.body).includes(ADMIN));
});
test('source event rate limit charges all batch members and provides retry-after', async (t) => {
  const { send, store } = await setup(t, { INGESTION_SOURCE_RATE: '2' });
  const response = await send('/v1/events/batch', { token: SOURCE, method: 'POST', body: { events: [input(), input({ sequence: 2 }), input({ sequence: 3 })] } });
  assert.equal(response.status, 429); assert.ok(Number(response.headers.get('retry-after')) > 0);
  assert.equal(store.metrics().events, 0);
});
test('backlog exhaustion returns retryable unavailable without partial acceptance', async (t) => {
  const { send, store } = await setup(t, { INGESTION_MAX_PENDING: '1' });
  const response = await send('/v1/events/batch', { token: SOURCE, method: 'POST', body: { events: [input(), input({ sequence: 2 })] } });
  assert.equal(response.status, 503); assert.equal(store.metrics().events, 0);
});
test('Kafka-disabled flush reports unavailable and administrative actions reject sources', async (t) => {
  const { send } = await setup(t);
  assert.equal((await send('/v1/outbox/flush', { method: 'POST', body: {} })).status, 503);
  assert.equal((await send('/v1/retention', { method: 'POST', token: SOURCE, body: {} })).status, 401);
});
test('security headers are present and permissive CORS is absent', async (t) => {
  const { send } = await setup(t); const response = await send('/health/live', { token: null });
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(response.headers.get('x-powered-by'), null);
  assert.equal(response.headers.get('access-control-allow-origin'), null);
});
test('internal errors expose no exception message or stack', async (t) => {
  const publisher = { enabled: true, flush: async () => { throw new Error('broker password secret123'); } };
  const { send } = await setup(t, {}, publisher);
  const response = await send('/v1/outbox/flush', { method: 'POST', body: {} });
  assert.equal(response.status, 500); assert.equal(response.body.error.code, 'INTERNAL_ERROR');
  assert.ok(!JSON.stringify(response.body).includes('secret123'));
});
test('broker unavailability during flush uses the same structured error contract', async (t) => {
  const { send } = await setup(t, {}, { enabled: true, flush: async () => ({ attempted: 1, published: 0, failed: 1 }) });
  const response = await send('/v1/outbox/flush', { method: 'POST', body: {} });
  assert.equal(response.status, 503); assert.equal(response.body.error.code, 'BROKER_UNAVAILABLE');
  assert.equal(response.body.requestId, response.headers.get('x-request-id'));
  assert.equal(response.body.error.details.failed, 1);
});
