import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventStore } from '../src/ingestion/store.js';
import { OutboxPublisher } from '../src/transport/publisher.js';
import { event } from './fixtures.js';

const NOW = Date.parse('2026-10-15T06:00:00Z');
function setup(t, adapter, options = {}) {
  let now = NOW; const store = new EventStore({ path: ':memory:', now: () => now, maxPending: 10 });
  const publisher = new OutboxPublisher({ store, adapter, now: () => now, maxAttempts: 2, baseDelayMs: 100, maxDelayMs: 1000, ...options });
  t.after(async () => { await publisher.stop(); store.close(); });
  return { store, publisher, advance: (ms) => { now += ms; } };
}
function input(overrides = {}) { return event({ sourceId: 'test-source', entityId: 'AIRCRAFT-01', ...overrides }, NOW); }
test('broker-disabled publisher never acknowledges durable pending records', async (t) => {
  const { store, publisher } = setup(t, null); store.acceptBatch([input()]);
  const result = await publisher.flush(); assert.equal(result.enabled, false);
  assert.equal(store.metrics().outbox.queued, 1); assert.equal(store.metrics().outbox.published, 0);
});
test('delivery publishes normalized topic/key/envelope then marks acknowledged records', async (t) => {
  const messages = []; const adapter = { send: async (message) => messages.push(message), close: async () => {} };
  const { store, publisher } = setup(t, adapter); const original = input(); store.acceptBatch([original]);
  const result = await publisher.flush(); assert.equal(result.published, 1);
  assert.equal(messages[0].topic, 'logistics.aircraft.v1'); assert.equal(messages[0].key, 'test-source:AIRCRAFT-01');
  assert.equal(messages[0].event.eventId, original.eventId); assert.equal(store.getEvent(original.eventId).delivery, 'published');
});
test('broker failure retains work, delays retry, dead-letters, and admin retry can recover', async (t) => {
  let fails = true; const adapter = { send: async () => { if (fails) throw new Error('private-broker-info'); }, close: async () => {} };
  const { store, publisher, advance } = setup(t, adapter); const original = input(); store.acceptBatch([original]);
  assert.equal((await publisher.flush()).failed, 1); assert.equal((await publisher.flush()).attempted, 0);
  advance(100); assert.equal((await publisher.flush()).failed, 1);
  assert.equal(store.getEvent(original.eventId).delivery, 'dead');
  assert.ok(!JSON.stringify(store.listOutbox({})).includes('private-broker-info'));
  store.retryDead(original.eventId); fails = false;
  assert.equal((await publisher.flush()).published, 1); assert.equal(store.getEvent(original.eventId).delivery, 'published');
});
test('overlapping flush requests share one in-flight drain instead of sending duplicates', async (t) => {
  let release; let calls = 0;
  const gate = new Promise((resolve) => { release = resolve; });
  const { store, publisher } = setup(t, { send: async () => { calls++; await gate; }, close: async () => {} });
  store.acceptBatch([input()]); const first = publisher.flush(); const second = publisher.flush(); release();
  const results = await Promise.all([first, second]);
  assert.equal(calls, 1); assert.equal(results[0].published, 1); assert.equal(results[1].published, 1);
});
test('bounded drain does not consume an unlimited backlog', async (t) => {
  const { store, publisher } = setup(t, { send: async () => {}, close: async () => {} }, { batchSize: 2 });
  store.acceptBatch([input({ entityId: 'A' }), input({ entityId: 'B' }), input({ entityId: 'C' })]);
  assert.equal((await publisher.flush()).published, 2); assert.equal(store.metrics().outbox.queued, 1);
});
test('stop waits for active acknowledgement before closing adapter and refuses future sends', async (t) => {
  let release; const gate = new Promise((resolve) => { release = resolve; }); let closed = false;
  const { store, publisher } = setup(t, { send: async () => gate, close: async () => { closed = true; } });
  store.acceptBatch([input()]); const drain = publisher.flush(); const stop = publisher.stop();
  assert.equal(closed, false); release(); await Promise.all([drain, stop]); assert.equal(closed, true);
  assert.equal((await publisher.flush()).attempted, 0);
});
test('shutdown still closes the adapter if a database failure follows broker acknowledgement', async (t) => {
  let closed = false;
  const { store, publisher } = setup(t, { send: async () => {}, close: async () => { closed = true; } });
  store.acceptBatch([input()]);
  store.markPublished = () => { throw new Error('disk failed after broker acknowledgement'); };
  const drain = publisher.flush();
  const stop = publisher.stop();
  await assert.rejects(drain, /disk failed/); await assert.rejects(stop, /disk failed/);
  assert.equal(closed, true); assert.equal(store.metrics().outbox.queued, 1);
  // The expected rejected shutdown is already asserted; don't repeat it in the generic teardown.
  publisher.stop = async () => {};
});
