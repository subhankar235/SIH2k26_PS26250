import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { startServer } from '../src/server.js';
import { runConsumer } from '../src/transport/consumer-cli.js';
const brokers = process.env.KAFKA_TEST_BROKERS || process.env.KAFKA_BROKERS;
if (!brokers) throw new Error('Relief pipeline smoke requires a real local test broker.');
const id = randomUUID(); const env = { ...process.env, HOST: '127.0.0.1', PORT: '31874', KAFKA_BROKERS: brokers, RELIEF_AI_MODE: 'deterministic',
  INGESTION_DB_PATH: `var/relief-smoke-${id}.sqlite`, CONSUMER_DB_PATH: `var/relief-reader-${id}.sqlite`, CONSUMER_GROUP_ID: `relief-smoke-${id}` };
let runtime, reader;
const post = async (path, body) => {
  const response = await fetch(`http://127.0.0.1:31874/v1/simulation/${path}`, { method: 'POST', redirect: 'error',
    headers: { Authorization: `Bearer ${env.INGESTION_ADMIN_TOKEN}`, 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(10000) });
  assert.ok(response.ok, `Simulation command failed: ${response.status}`); return response.json();
};
try {
  runtime = await startServer(env); reader = await runConsumer(env);
  const command = { scenario: 'civilian-relief', commandId: randomUUID() };
  let state = await post('start', command); assert.equal((await post('start', command)).command.replayed, true);
  const scores = [state.plan.objective.servedPriority]; const runId = state.world.runId;
  while (state.nextPhase) {
    state = await post('step', { commandId: randomUUID(), runId, expectedRevision: state.world.revision, phase: state.nextPhase });
    assert.equal(state.validation.valid, true); scores.push(state.plan.objective.servedPriority);
  }
  assert.deepEqual(scores, [9, 7, 7, 0, 10, 0]); assert.equal(runtime.store.metrics().events, 98);
  while (runtime.store.metrics().outbox.queued) assert.equal((await runtime.publisher.flush()).failed, 0);
  const end = Date.now() + 25000;
  const count = () => reader.store.db.prepare('SELECT COUNT(*) AS n FROM consumer_events WHERE entity_id LIKE ?').get(`relief-${runId}-%`).n;
  while (count() !== 98) { if (Date.now() > end) throw new Error('Relief reader delivery timed out.'); await delay(100); }
  assert.equal(runtime.store.metrics().outbox.published, 98); assert.equal(reader.store.latest({ limit: 1000 }).filter((r) => r.event.entityId.startsWith(`relief-${runId}-`)).length, 17);
  console.log('Real civilian simulation HTTP→atomic events/outbox→Kafka→reader passed all6revisions/98events; plans independently verified and command replay idempotent.');
} finally {
  const results = await Promise.allSettled([reader?.stop(), runtime?.close()]);
  if (results.some((r) => r.status === 'rejected')) { process.exitCode = 1; console.error('Relief smoke cleanup failed.'); }
}
