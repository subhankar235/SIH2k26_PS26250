import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { startServer } from '../src/server.js';
import { runConsumer } from '../src/consumer-cli.js';
import { EVENT_TYPES } from '../src/contracts.js';
import { sampleEvent } from '../src/sample-events.js';

const brokers = process.env.KAFKA_TEST_BROKERS || process.env.KAFKA_BROKERS;
if (!brokers) throw new Error('Real pipeline smoke requires KAFKA_TEST_BROKERS or KAFKA_BROKERS.');
const runId = randomUUID(); const prefix = `fixture-${runId.slice(0, 8)}-`;
const env = { ...process.env, HOST: '127.0.0.1', PORT: '31872', KAFKA_BROKERS: brokers,
  INGESTION_DB_PATH: `var/pipeline-${runId}.sqlite`, CONSUMER_DB_PATH: `var/reader-${runId}.sqlite`, CONSUMER_GROUP_ID: `pipeline-${runId}` };
const sources = JSON.parse(env.INGESTION_SOURCES_JSON ?? '[]');
let server, reader;
async function until(predicate) {
  const end = Date.now() + 25000;
  while (!predicate()) { if (Date.now() >= end) throw new Error('Pipeline reader timed out.'); await delay(100); }
}
async function post(event) {
  const source = sources.find((s) => s.sourceId === event.sourceId);
  const response = await fetch('http://127.0.0.1:31872/v1/events', { method: 'POST',
    headers: { Authorization: `Bearer ${source.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(event), signal: AbortSignal.timeout(10000) });
  assert.ok(response.ok, `Ingestion failed: ${response.status}`); return response.json();
}
try {
  server = await startServer(env); reader = await runConsumer(env);
  const input = EVENT_TYPES.map((type) => {
    const source = sources.find((s) => s.types.includes(type));
    if (!source) throw new Error(`Missing source for ${type}.`);
    return sampleEvent(type, { sourceId: source.sourceId, entityId: prefix + type.split('.')[0] });
  });
  for (const event of input) assert.equal((await post(event)).duplicate, false);
  const delivered = await server.publisher.flush(); assert.equal(delivered.failed, 0);
  const own = () => reader.store.latest({ limit: 1000 }).filter((r) => r.event.entityId.startsWith(prefix));
  await until(() => own().length === 5);
  const weather = { ...input[2], eventId: randomUUID(), sequence: 2, observedAt: new Date().toISOString(), data: { ...input[2].data, condition: 'rain' } };
  await post(weather); assert.equal((await post(weather)).duplicate, true);
  assert.equal((await server.publisher.flush()).failed, 0);
  await until(() => own().some((r) => r.event.eventId === weather.eventId));
  assert.equal(server.store.metrics().events, 6);
  assert.equal(reader.store.db.prepare('SELECT COUNT(*) AS count FROM consumer_events WHERE entity_id LIKE ?').get(`${prefix}%`).count, 6);
  assert.equal(server.store.metrics().outbox.published, 6);
  await reader.stop(); reader = await runConsumer(env);
  assert.equal(own().length, 5);
  assert.equal(own().find((r) => r.event.type === 'weather.observation').event.data.condition, 'rain');
  console.log('Real HTTP → SQLite outbox → Kafka → independent durable reader smoke passed for all five domains, update, duplicate and reader restart.');
} finally {
  const results = await Promise.allSettled([reader?.stop(), server?.close()]);
  if (results.some((r) => r.status === 'rejected')) { process.exitCode = 1; console.error('Pipeline cleanup failed.'); }
}
