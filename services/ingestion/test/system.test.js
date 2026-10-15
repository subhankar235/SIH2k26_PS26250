import test from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes, randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../src/app.js';
import { loadConfig } from '../src/platform/config.js';
import { EventStore } from '../src/ingestion/store.js';
import { OutboxPublisher } from '../src/transport/publisher.js';
import { EVENT_TYPES } from '../src/contracts/events.js';
import { ReliefSimulationService } from '../src/planning/service.js';
import { validateReliefPlan } from '../src/planning/planner.js';
import { validateReliefNegotiationReport } from '../src/agents/negotiation.js';
import { createReliefAnnotator, loadReliefAIConfig } from '../src/agents/annotations.js';

test('isolated system journey: HTTP input, negotiation, dashboard, expiry and persisted recovery', async t => {
  const directory = mkdtempSync(join(tmpdir(), 'logistics-system-'));
  const token = () => randomBytes(36).toString('base64url');
  const admin = token(), viewer = token();
  const sources = EVENT_TYPES.map((type, index) => ({ sourceId: `demo-${index}`, token: token(), types: [type] }));
  const config = loadConfig({ INGESTION_ADMIN_TOKEN: admin, MONITOR_VIEWER_TOKEN: viewer,
    INGESTION_SOURCES_JSON: JSON.stringify(sources), INGESTION_DB_PATH: join(directory, 'events.sqlite') });
  let clock = Date.now(), runtime;
  const now = () => clock;
  async function open() {
    const store = new EventStore({ path: config.dbPath, now });
    const simulation = new ReliefSimulationService({ store, sources: config.sources, now,
      annotator: createReliefAnnotator(loadReliefAIConfig({})) });
    const publisher = new OutboxPublisher({ store, now });
    const server = createApp({ config, store, simulation, publisher, now }).listen(0, '127.0.0.1');
    runtime = { store, simulation, publisher, server };
    await once(server, 'listening');
    runtime.base = `http://127.0.0.1:${server.address().port}`;
  }
  async function close() {
    if (!runtime) return;
    const current = runtime; runtime = null;
    try {
      await Promise.all([new Promise(resolve => current.server.close(resolve)),
        current.simulation.close(), current.publisher.stop()]);
    } finally { current.store.close(); }
  }
  t.after(async () => { try { await close(); } finally { rmSync(directory, { recursive: true, force: true }); } });
  async function send(path, { body, credential = admin, cookie } = {}) {
    return fetch(runtime.base + path, { method: body ? 'POST' : 'GET', redirect: 'error',
      headers: { ...(credential ? { Authorization: `Bearer ${credential}` } : {}),
        ...(body ? { 'Content-Type': 'application/json', Origin: runtime.base } : {}), ...(cookie ? { Cookie: cookie } : {}) },
      body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(10000) });
  }
  async function json(path, options) {
    const response = await send(path, options);
    assert.ok(response.ok, `${path}: HTTP ${response.status}`);
    return response.json();
  }
  await open();
  const start = await json('/v1/simulation/start', { body: {
    scenario: 'civilian-relief', inputMode: 'gateway', commandId: randomUUID() } });
  assert.equal(start.plan.objective.servedPriority, 9);
  assert.equal(validateReliefNegotiationReport(start.world, start.negotiation).valid, true);
  for (const kind of ['proposal', 'reject', 'bid', 'counterproposal', 'accept', 'commit']) {
    assert.ok(start.negotiation.messages.some(message => message.kind === kind), kind);
  }
  assert.equal(start.demand.modelId, 'synthetic-demand-ols');
  assert.ok(Number.isFinite(start.demand.predictedRequests));
  assert.ok(start.demand.evaluation.mae < start.demand.evaluation.baselineMae);
  const weatherSource = sources.find(source => source.sourceId === start.inputs.authorities['weather.observation']);
  function weather(airport, sequence, storm = false, ttl = 60000) {
    return { schemaVersion: 1, eventId: randomUUID(), sourceId: weatherSource.sourceId,
      type: 'weather.observation', entityId: start.inputs.namespace + airport, sequence,
      observedAt: new Date(clock).toISOString(), validUntil: new Date(clock + ttl).toISOString(),
      data: { temperatureC: 24, windSpeedMps: storm ? 25 : 5, visibilityM: storm ? 1500 : 10000, condition: storm ? 'storm' : 'clear' } };
  }
  const storm = weather('SIM-CLINIC', 1, true);
  await json('/v1/events', { body: storm, credential: weatherSource.token });
  assert.equal((await json('/v1/events', { body: storm, credential: weatherSource.token })).duplicate, true);
  assert.equal(runtime.simulation.snapshot().world.revision, 1);
  assert.equal(runtime.simulation.snapshot().plan.objective.servedPriority, 7);
  await json('/v1/events/batch', { credential: weatherSource.token, body: { events: [
    weather('SIM-CLINIC', 2, false, 1000), weather('SIM-SHELTER', 1, true) ] } });
  assert.equal(runtime.simulation.snapshot().world.revision, 2);
  assert.equal(runtime.simulation.snapshot().plan.objective.servedPriority, 6);
  clock += 1001;
  assert.equal(runtime.simulation.snapshot().planUsable, false);
  runtime.simulation.expireInputs();
  assert.equal(runtime.simulation.snapshot().world.revision, 3);
  assert.equal(runtime.simulation.snapshot().plan.objective.servedPriority, 0);
  await json('/v1/events/batch', { credential: weatherSource.token, body: { events: [
    weather('SIM-CLINIC', 3), weather('SIM-SHELTER', 2) ] } });
  const recovered = runtime.simulation.snapshot();
  assert.equal(recovered.world.revision, 4);
  assert.equal(recovered.plan.objective.servedPriority, 9);
  assert.equal(recovered.negotiation.outcome.verified, true);
  assert.equal(validateReliefPlan(recovered.world, recovered.plan).valid, true);
  for (const asset of ['', 'app.js', 'relief.js', 'styles.css']) {
    assert.equal((await send('/monitor/' + asset, { credential: null })).status, 200);
  }
  assert.equal((await send('/monitor/api/simulation', { credential: null })).status, 401);
  const login = await send('/monitor/session', { credential: null, body: { token: viewer } });
  assert.equal(login.status, 200);
  const cookie = login.headers.get('set-cookie').split(';')[0];
  assert.equal((await json('/monitor/api/simulation', { credential: null, cookie })).world.revision, 4);
  assert.equal((await send('/v1/events', { body: weather('SIM-CLINIC', 4), credential: viewer, cookie })).status, 401);
  assert.equal((await runtime.publisher.flush()).enabled, false);
  const metrics = runtime.store.metrics();
  assert.ok(metrics.outbox.queued > 0);
  assert.equal(metrics.outbox.published, 0);
  const report = JSON.stringify(recovered.negotiation);
  await close(); await open();
  const restored = await json('/v1/simulation');
  assert.equal(restored.world.runId, start.world.runId);
  assert.equal(restored.world.revision, 4);
  assert.equal(JSON.stringify(restored.negotiation), report);
  assert.equal(runtime.store.metrics().outbox.queued, metrics.outbox.queued);
  assert.equal((await send('/monitor/api/simulation', { credential: null, cookie })).status, 401);
  assert.equal((await send('/health/ready', { credential: null })).status, 200);
  console.log(JSON.stringify({ systemJourney: 'passed', scores: [9, 7, 6, 0, 9], revisions: 5,
    sourceReplay: true, expiry: 'injected-clock', dashboard: true, restart: true, kafka: 'disabled-events-remain-queued' }));
});
