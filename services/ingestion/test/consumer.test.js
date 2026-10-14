import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ConsumerStore } from '../src/consumer-store.js';
import { KafkaReadModelWorker } from '../src/consumer.js';
import { TOPICS } from '../src/contracts.js';
import { event } from './fixtures.js';

const now = Date.parse('2026-10-15T10:00:00Z');
const record = (input = event({}, now), offset = '0', changes = {}) => ({
  topic: TOPICS[input.type], partition: 0,
  message: { offset, key: Buffer.from(`${input.sourceId}:${input.entityId}`), value: Buffer.from(JSON.stringify(input)) },
  ...changes,
});
const create = (t, options = {}) => {
  const store = new ConsumerStore({ path: ':memory:', groupId: 'test-reader', now: () => now, ...options });
  t.after(() => store.close()); return store;
};

test('stores record, dedupe, latest and arbitrarily precise checkpoint atomically', (t) => {
  const store = create(t); const input = event({}, now); const offset = '9007199254740993';
  assert.equal(store.process(record(input, offset)).disposition, 'current');
  assert.equal(store.checkpoint(TOPICS[input.type], 0), '9007199254740994');
  assert.deepEqual(store.latest()[0].event, input);
  assert.equal(store.process(record(input, '9007199254740994')).disposition, 'duplicate');
  assert.equal(store.stats().events, 1);
  assert.equal(store.process(record(input, '9007199254740994')).disposition, 'replayed');
  assert.equal(store.process(record(input, offset)).disposition, 'replayed');
});

test('restart preserves replay checkpoint and dedupe across partitions', (t) => {
  const folder = mkdtempSync(join(tmpdir(), 'consumer-'));
  const options = { path: join(folder, 'reader.sqlite'), groupId: 'restart', now: () => now };
  const input = event({}, now); let store = new ConsumerStore(options);
  store.process(record(input)); store.close(); store = new ConsumerStore(options);
  t.after(() => { store.close(); rmSync(folder, { recursive: true, force: true }); });
  assert.equal(store.process(record(input)).disposition, 'replayed');
  assert.equal(store.process(record(input, '0', { partition: 1 })).disposition, 'duplicate');
  assert.equal(store.stats().events, 1); assert.equal(store.latest().length, 1);
});

test('reordering, expiry and source isolation preserve reported latest state', (t) => {
  const store = create(t); const fresh = event({ sequence: 5 }, now);
  store.process(record(fresh));
  assert.equal(store.process(record(event({ sequence: 4 }, now), '1')).disposition, 'stale');
  assert.equal(store.process(record(event({ sequence: 6, observedAt: new Date(now - 5000).toISOString() }, now), '2')).disposition, 'stale');
  assert.equal(store.process(record(event({ sequence: 7, observedAt: new Date(now - 7000).toISOString(), validUntil: new Date(now - 1).toISOString() }, now), '3')).disposition, 'expired');
  store.process(record(event({ sourceId: 'source-2' }, now), '4'));
  assert.equal(store.latest().length, 2); assert.equal(store.latest()[0].event.eventId, fresh.eventId);
});

test('invalid JSON, schema, topic, key and conflicting event ID are safely quarantined', (t) => {
  const store = create(t); const input = event({}, now); store.process(record(input));
  const cases = [
    { ...record(input, '1'), message: { offset: '1', key: Buffer.from('secret-password'), value: Buffer.from('{"secret-password":') } },
    record({ ...input, credential: 'secret-password' }, '2'),
    record(input, '3', { topic: TOPICS['crew.availability'] }),
    { ...record(input, '4'), message: { ...record(input, '4').message, key: Buffer.from('secret-password') } },
    record({ ...input, data: { ...input.data, capacityKg: 20 } }, '5'),
  ];
  for (const item of cases) assert.equal(store.process(item).disposition, 'quarantined');
  assert.equal(store.stats().quarantine, 5);
  assert.doesNotMatch(JSON.stringify(store.quarantined()), /secret-password|credential|capacityKg/);
  assert.equal(store.latest()[0].event.eventId, input.eventId);
});

test('oversized payload is bounded and quarantined without parsing or storing raw content', (t) => {
  const store = create(t, { maxMessageBytes: 1024 }); const item = record();
  item.message.value = Buffer.alloc(1025, 's');
  assert.equal(store.process(item).reason, 'MESSAGE_TOO_LARGE');
  assert.equal(store.quarantined()[0].valueBytes, 1025);
  assert.ok(JSON.stringify(store.quarantined()).length < 500);
});

test('capacity exhaustion fails without advancing a checkpoint or deleting evidence', (t) => {
  const store = create(t, { maxEvents: 1, maxQuarantine: 1 }); store.process(record());
  assert.throws(() => store.process(record(event({ sequence: 2 }, now), '1')), { code: 'CONSUMER_CAPACITY' });
  assert.equal(store.checkpoint(TOPICS['aircraft.status'], 0), '1');
  const bad = record(event({ sequence: 2 }, now), '1'); bad.message.value = Buffer.from('invalid'); store.process(bad);
  bad.message.offset = '2'; assert.throws(() => store.process(bad), { code: 'CONSUMER_CAPACITY' });
  assert.equal(store.checkpoint(bad.topic, 0), '2'); assert.equal(store.stats().events, 1); assert.equal(store.stats().quarantine, 1);
});

test('a transaction failure rolls back record, projection and checkpoint', (t) => {
  const store = create(t);
  store.db.exec("CREATE TRIGGER reject_checkpoint BEFORE INSERT ON consumer_checkpoints BEGIN SELECT RAISE(ABORT, 'injected checkpoint failure'); END;");
  assert.throws(() => store.process(record()), /injected checkpoint failure/);
  assert.equal(store.stats().events, 0); assert.equal(store.latest().length, 0); assert.equal(store.checkpoint(TOPICS['aircraft.status'], 0), null);
});

test('invalid broker coordinates fail safely without checkpoint changes', (t) => {
  const store = create(t);
  for (const offset of ['-1', '1.1', '1e3', '01', '9223372036854775807']) {
    assert.throws(() => store.process(record(undefined, offset)), { code: 'CONSUMER_COORDINATES' });
  }
  assert.throws(() => store.process(record(undefined, '0', { partition: -1 })), { code: 'CONSUMER_COORDINATES' });
});

test('worker commits only durable results, and stops the batch on store failure', async (t) => {
  const store = create(t, { maxEvents: 1 }); const commits = []; let runOptions;
  const consumer = { connect: async () => {}, subscribe: async () => {}, run: async (options) => { runOptions = options; },
    commitOffsets: async (items) => { assert.equal(store.checkpoint(items[0].topic, 0), items[0].offset); commits.push(items); },
    stop: async () => {}, disconnect: async () => {} };
  const worker = new KafkaReadModelWorker({ store, consumer }); await worker.start();
  assert.equal(runOptions.autoCommit, false); assert.equal(runOptions.eachBatchAutoResolve, false);
  const inputs = [record(), record(event({ sequence: 2 }, now), '1')];
  await assert.rejects(runOptions.eachBatch({ batch: { topic: inputs[0].topic, partition: 0, messages: inputs.map((item) => item.message) },
    isRunning: () => true, isStale: () => false, heartbeat: async () => {}, resolveOffset: () => {} }), { code: 'CONSUMER_CAPACITY' });
  assert.equal(commits.length, 1); assert.equal(commits[0][0].offset, '1'); await worker.stop();
});

test('broker commit failure is replayable with no duplicated state', async (t) => {
  const store = create(t); let fail = true;
  const consumer = { commitOffsets: async () => { if (fail) throw new Error('broker disconnected'); } };
  const worker = new KafkaReadModelWorker({ store, consumer }); const item = record();
  await assert.rejects(worker.process(item), /broker disconnected/); fail = false;
  assert.equal((await worker.process(item)).disposition, 'replayed'); assert.equal(store.stats().events, 1);
});

test('SQLite size limit fails atomically and ownership excludes another connection or group', (t) => {
  const folder = mkdtempSync(join(tmpdir(), 'consumer-owned-'));
  const path = join(folder, 'reader.sqlite'); const options = { path, groupId: 'owner', now: () => now, maxDatabaseBytes: 1048576 };
  const store = new ConsumerStore(options); t.after(() => { store.close(); rmSync(folder, { recursive: true, force: true }); });
  assert.throws(() => new ConsumerStore(options), /locked/);
  let offset = 0;
  for (;;) {
    try { store.process(record(event({ entityId: `item-${offset}` }, now), String(offset))); offset++; }
    catch (failure) { assert.match(failure.message, /full/); break; }
    assert.ok(offset < 3000, 'database must saturate before unbounded growth');
  }
  assert.equal(store.stats().events, offset); assert.equal(store.checkpoint(TOPICS['aircraft.status'], 0), String(offset));
  store.close(); assert.throws(() => new ConsumerStore({ ...options, groupId: 'different' }), { code: 'CONSUMER_DATABASE_NOT_OWNED' });
});

test('checkpoint capacity and malformed UTF8 are bounded without unsafe metadata', (t) => {
  const store = create(t, { maxCheckpoints: 1 }); const item = record(); item.message.value = Buffer.from([0xff]);
  assert.equal(store.process(item).reason, 'INVALID_JSON');
  assert.throws(() => store.process(record(undefined, '0', { partition: 1 })), { code: 'CONSUMER_CAPACITY' });
  assert.equal(store.stats().checkpoints, 1); assert.equal(store.stats().quarantine, 1);
});

test('a stale batch never persists or acknowledges messages', async (t) => {
  const store = create(t); let runOptions; let commits = 0;
  const consumer = { connect: async () => {}, subscribe: async () => {}, run: async (options) => { runOptions = options; },
    commitOffsets: async () => { commits++; }, stop: async () => {}, disconnect: async () => {} };
  const worker = new KafkaReadModelWorker({ store, consumer }); await worker.start(); const item = record();
  await runOptions.eachBatch({ batch: { topic: item.topic, partition: 0, messages: [item.message] },
    isRunning: () => true, isStale: () => true, heartbeat: async () => {}, resolveOffset: () => {} });
  assert.equal(store.stats().events, 0); assert.equal(commits, 0); await worker.stop();
});
