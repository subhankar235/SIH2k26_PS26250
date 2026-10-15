import { test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { randomUUID } from 'node:crypto';
import { EventStore } from '../src/ingestion/store.js';
import { createApp } from '../src/app.js';
import { loadConfig } from '../src/platform/config.js';
import { createReliefAnnotator, loadReliefAIConfig } from '../src/agents/annotations.js';
import { ReliefSimulationService } from '../src/planning/service.js';
import { EVENT_TYPES } from '../src/contracts/events.js';

test('simulation mutations require admin, viewers only read, and strict command contracts guard revisions', async (t) => {
  const admin = 'a'.repeat(48), viewer = 'v'.repeat(48);
  const sources = EVENT_TYPES.map((type, i) => ({ sourceId: `test-${i}`, token: String(i).repeat(48), types: [type] }));
  const config = loadConfig({ INGESTION_ADMIN_TOKEN: admin, MONITOR_VIEWER_TOKEN: viewer, INGESTION_SOURCES_JSON: JSON.stringify(sources) });
  const store = new EventStore({ path: ':memory:' });
  const simulation = new ReliefSimulationService({ store, sources: config.sources, annotator: createReliefAnnotator(loadReliefAIConfig({})) });
  const server = createApp({ config, store, simulation, publisher: { enabled: false } }).listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(async () => { await new Promise((resolve) => server.close(resolve)); await simulation.close(); store.close(); });
  const base = `http://127.0.0.1:${server.address().port}`;
  const send = (path, { token = admin, body, cookie } = {}) => fetch(base + path, { method: body ? 'POST' : 'GET',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { 'Content-Type': 'application/json', Origin: base } : {}), ...(cookie ? { Cookie: cookie } : {}) },
    body: body ? JSON.stringify(body) : undefined });
  const command = { scenario: 'civilian-relief', commandId: randomUUID() };
  for (const token of [null, viewer, sources[0].token]) assert.equal((await send('/v1/simulation/start', { token, body: command })).status, 401);
  assert.equal((await send('/v1/simulation/start', { body: { ...command, world: {} } })).status, 422);
  assert.equal((await send('/v1/simulation/start', { body: command })).status, 201);
  assert.equal((await send('/v1/simulation/start', { body: command })).status, 200);
  const login = await send('/monitor/session', { token: null, body: { token: viewer } });
  const cookie = login.headers.get('set-cookie').split(';')[0];
  const view = await send('/monitor/api/simulation', { token: null, cookie }); assert.equal(view.status, 200);
  assert.match(view.headers.get('cache-control'), /no-store/); const state = await view.json();
  assert.equal(state.world.simulation, true); assert.equal(state.validation.valid, true);
  assert.equal((await send('/v1/simulation/step', { token: null, cookie, body: { commandId: randomUUID(), runId: state.world.runId, expectedRevision: 0, phase: 'weather-change' } })).status, 401);
  assert.equal((await send('/monitor/api/simulation?unknown=yes', { token: null, cookie })).status, 422);
  assert.equal((await send('/monitor/api/simulation', { token: null })).status, 401);
  assert.equal((await send('/v1/simulation/step', { body: { commandId: randomUUID(), runId: state.world.runId, expectedRevision: 1, phase: 'weather-change' } })).status, 409);
});
