import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { EventStore } from '../src/store.js';
import { ReliefSimulationService } from '../src/relief-service.js';
import { EVENT_TYPES } from '../src/contracts.js';
import { RELIEF_PHASES } from '../src/relief-world.js';
const NOW = Date.parse('2026-10-15T06:00:00Z');
const sources = EVENT_TYPES.map((type) => ({ sourceId: `relief-${type.split('.')[0]}`, types: [type] }));
const annotator = () => ({ annotate: async (x) => ({ ...x, mode: 'deterministic', modelsUsed: [], highlights: [], generatedAt: new Date(NOW).toISOString() }), close: async () => {} });
function setup(t, options = {}) {
  const store = new EventStore({ path: ':memory:', now: () => NOW, ...options });
  const service = new ReliefSimulationService({ store, sources, now: () => NOW, annotator: annotator() });
  t.after(async () => { await service.close(); store.close(); }); return { store, service };
}
test('simulation start and each fixed phase persist validated plans with atomic typed events', async (t) => {
  const { store, service } = setup(t); assert.deepEqual(service.snapshot(), { status: 'idle' });
  let current = service.start({ scenario: 'civilian-relief', commandId: randomUUID() });
  assert.equal(current.world.simulation, true); assert.equal(current.validation.valid, true);
  assert.equal(store.metrics().events, 16); assert.equal(current.plan.objective.servedPriority, 9);
  const objectives = [];
  for (const phase of RELIEF_PHASES) {
    current = service.step({ commandId: randomUUID(), runId: current.world.runId, expectedRevision: current.world.revision, phase });
    assert.equal(current.validation.valid, true); objectives.push(current.plan.objective.servedPriority);
  }
  assert.deepEqual(objectives, [7, 7, 0, 10, 0]); assert.equal(current.history.length, 6);
  assert.equal(current.nextPhase, null); assert.ok(current.demand.simulation);
});
test('idempotent command receipts and run/revision/order guards preserve state', (t) => {
  const { service, store } = setup(t); const command = { scenario: 'civilian-relief', commandId: randomUUID() };
  const start = service.start(command); const before = store.metrics().events;
  assert.equal(service.start(command).world.runId, start.world.runId); assert.equal(store.metrics().events, before);
  assert.throws(() => service.start({ ...command, replaceRunId: start.world.runId }), (e) => e.status === 409);
  assert.throws(() => service.start({ scenario: 'civilian-relief', commandId: randomUUID() }), (e) => e.status === 409);
  for (const overrides of [{ runId: randomUUID() }, { expectedRevision: 1 }, { phase: 'airport-closure' }]) {
    assert.throws(() => service.step({ commandId: randomUUID(), runId: start.world.runId, expectedRevision: 0, phase: 'weather-change', ...overrides }), (e) => e.status === 409);
  }
  assert.equal(service.snapshot().world.revision, 0); assert.equal(store.metrics().events, before);
});
test('state write failure rolls back gateway history, outbox and command receipt', (t) => {
  const { service, store } = setup(t);
  store.db.exec("CREATE TRIGGER fail_sim_state BEFORE INSERT ON relief_state BEGIN SELECT RAISE(ABORT,'failure'); END;");
  assert.throws(() => service.start({ scenario: 'civilian-relief', commandId: randomUUID() }));
  assert.equal(store.metrics().events, 0); assert.equal(store.metrics().outbox.queued, 0);
  assert.equal(store.db.prepare('SELECT COUNT(*) AS n FROM relief_commands').get().n, 0);
  assert.deepEqual(service.snapshot(), { status: 'idle' });
});
test('backlog saturation atomically refuses a new simulation', (t) => {
  const { service, store } = setup(t, { maxPending: 1 });
  assert.throws(() => service.start({ scenario: 'civilian-relief', commandId: randomUUID() }), (e) => e.status === 503);
  assert.equal(store.metrics().events, 0); assert.deepEqual(service.snapshot(), { status: 'idle' });
});
test('persisted simulation and command replay survive service/store restart', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'relief-persist-')); const path = join(directory, 'events.sqlite');
  const command = { scenario: 'civilian-relief', commandId: randomUUID() };
  let store = new EventStore({ path, now: () => NOW });
  let service = new ReliefSimulationService({ store, sources, now: () => NOW, annotator: annotator() });
  const start = service.start(command); await service.close(); store.close();
  store = new EventStore({ path, now: () => NOW });
  service = new ReliefSimulationService({ store, sources, now: () => NOW, annotator: annotator() });
  try { assert.equal(service.snapshot().world.runId, start.world.runId); service.start(command); assert.equal(store.metrics().events, 16); }
  finally { await service.close(); store.close(); }
});

test('slow obsolete annotations cannot attach to a newer revision', async (t) => {
  const store = new EventStore({ path: ':memory:', now: () => NOW }); let release;
  let count = 0;
  const provider = { annotate: async (input) => {
    if (++count === 1) await new Promise((resolve) => { release = resolve; });
    return { runId: input.runId, revision: input.revision, mode: 'deterministic', modelsUsed: [], highlights: [] };
  }, close: async () => { release?.(); } };
  const service = new ReliefSimulationService({ store, sources, now: () => NOW, annotator: provider });
  t.after(async () => { await service.close(); store.close(); });
  const start = service.start({ scenario: 'civilian-relief', commandId: randomUUID() });
  service.step({ commandId: randomUUID(), runId: start.world.runId, expectedRevision: 0, phase: 'weather-change' });
  release(); await service.task;
  assert.equal(service.snapshot().annotations.revision, 1); assert.equal(count, 2);
});

test('retained command capacity fails closed before fixture writes', (t) => {
  const { store, service } = setup(t);
  const statement = store.db.prepare('INSERT INTO relief_commands VALUES(?,?,?)');
  store.transaction(() => { for (let i = 0; i < 1000; i++) statement.run(randomUUID(), 'test', '{}'); });
  assert.throws(() => service.start({ scenario: 'civilian-relief', commandId: randomUUID() }), (e) => e.code === 'SIMULATION_COMMAND_CAPACITY');
  assert.equal(store.metrics().events, 0); assert.deepEqual(service.snapshot(), { status: 'idle' });
});

test('poisoned fixture sequence refuses the entire phase instead of silently losing Kafka delivery', (t) => {
  const { store, service } = setup(t);
  const initial = service.start({ scenario: 'civilian-relief', commandId: randomUUID() });
  const prior = store.listState({ type: 'aircraft.status' }).items[0].event;
  store.acceptBatch([{ ...prior, eventId: randomUUID(), sequence: 99 }]);
  const events = store.metrics().events;
  assert.throws(() => service.step({ commandId: randomUUID(), runId: initial.world.runId, expectedRevision: 0, phase: 'weather-change' }), (e) => e.code === 'SIMULATION_FIXTURE_CONFLICT');
  assert.equal(store.metrics().events, events); assert.equal(service.snapshot().world.revision, 0);
});
