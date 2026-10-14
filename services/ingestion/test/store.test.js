import assert from 'node:assert/strict';
import { test } from 'node:test';
import { randomUUID } from 'node:crypto';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { EventStore } from '../src/store.js';

const NOW = Date.parse('2026-10-15T06:00:00.000Z');
function event(overrides = {}) {
  return { schemaVersion: 1, eventId: randomUUID(), sourceId: 'fleet-feed', type: 'aircraft.status',
    entityId: 'AIRCRAFT-01', sequence: 1, observedAt: new Date(NOW - 1000).toISOString(),
    validUntil: new Date(NOW + 60000).toISOString(),
    data: { status: 'available', airportId: 'AIRPORT-A', capacityKg: 1200 }, ...overrides };
}
function store(t, options = {}) {
  const db = new EventStore({ path: ':memory:', now: () => NOW, maxPending: 10, ...options });
  t.after(() => db.close());
  return db;
}

test('acceptance atomically creates history, latest state, and queued delivery', (t) => {
  const db = store(t); const input = event(); const [receipt] = db.acceptBatch([input]);
  assert.equal(receipt.disposition, 'current'); assert.equal(receipt.delivery, 'queued');
  assert.equal(receipt.duplicate, false);
  assert.deepEqual(db.getEvent(input.eventId).event, input);
  assert.equal(db.listState({}).items[0].event.eventId, input.eventId);
  assert.equal(db.pending({}).length, 1);
});
test('exact retry returns same cursor and does not duplicate outgoing work', (t) => {
  const db = store(t); const input = event(); const [first] = db.acceptBatch([input]);
  const [retry] = db.acceptBatch([{ ...input, data: { capacityKg: 1200, airportId: 'AIRPORT-A', status: 'available' } }]);
  assert.equal(retry.cursor, first.cursor); assert.equal(retry.duplicate, true);
  assert.equal(db.listEvents({}).items.length, 1); assert.equal(db.pending({}).length, 1);
});
test('event ID reused for different content raises conflict without revealing stored data', (t) => {
  const db = store(t); const input = event(); db.acceptBatch([input]);
  assert.throws(() => db.acceptBatch([{ ...input, sourceId: 'other-feed' }]), (e) => e.status === 409 && e.code === 'EVENT_ID_CONFLICT' && !JSON.stringify(e.details ?? []).includes('fleet-feed'));
  assert.equal(db.listEvents({}).items.length, 1);
});
test('a conflict late in a batch rolls back earlier writes and projections', (t) => {
  const db = store(t); const existing = event(); db.acceptBatch([existing]); const next = event({ sequence: 2 });
  assert.throws(() => db.acceptBatch([next, { ...existing, sequence: 3 }]), { code: 'EVENT_ID_CONFLICT' });
  assert.equal(db.getEvent(next.eventId), null);
  assert.equal(db.listState({}).items[0].event.eventId, existing.eventId);
  assert.equal(db.pending({}).length, 1);
});
test('stale sequence and older observation are archived without overwriting state', (t) => {
  const db = store(t); const current = event({ sequence: 5 }); db.acceptBatch([current]);
  const results = db.acceptBatch([event({ sequence: 4 }), event({ sequence: 6, observedAt: new Date(NOW - 2000).toISOString() })]);
  assert.deepEqual(results.map((r) => r.disposition), ['stale', 'stale']);
  assert.equal(db.listState({}).items[0].event.eventId, current.eventId);
  assert.equal(db.pending({}).length, 1); assert.equal(db.listEvents({}).items.length, 3);
});
test('expired observation is recorded but never becomes latest or queued', (t) => {
  const db = store(t); const [result] = db.acceptBatch([event({ observedAt: new Date(NOW - 3000).toISOString(), validUntil: new Date(NOW).toISOString() })]);
  assert.equal(result.disposition, 'expired'); assert.equal(result.delivery, 'not_queued');
  assert.equal(db.listState({}).items.length, 0); assert.equal(db.pending({}).length, 0);
});
test('different sources and types keep independent sequence spaces', (t) => {
  const db = store(t); db.acceptBatch([event({ sequence: 50 }), event({ sourceId: 'fleet-backup', sequence: 1 })]);
  assert.equal(db.listState({}).items.length, 2);
  assert.equal(db.listState({ sourceId: 'fleet-backup' }).items[0].event.sequence, 1);
});
test('sequence gap quality warning is retained with the receipt', (t) => {
  const db = store(t); db.acceptBatch([event()]); const [result] = db.acceptBatch([event({ sequence: 3 })]);
  assert.ok(result.warnings.includes('sequence_gap'));
});
test('backlog cap rolls back whole batch but still permits duplicate retries', (t) => {
  const db = store(t, { maxPending: 1 }); const first = event();
  assert.throws(() => db.acceptBatch([first, event({ sequence: 2 })]), { code: 'BACKLOG_FULL' });
  assert.equal(db.listEvents({}).items.length, 0);
  db.acceptBatch([first]); assert.equal(db.acceptBatch([first])[0].duplicate, true);
});
test('duplicate within a single batch creates only one event and outbox row', (t) => {
  const db = store(t); const input = event(); const result = db.acceptBatch([input, input]);
  assert.deepEqual(result.map((r) => r.duplicate), [false, true]); assert.equal(db.pending({}).length, 1);
});
test('cursor pagination and filters replay immutable history without publishing again', (t) => {
  const db = store(t); db.acceptBatch([event(), event({ sequence: 2 }), event({ sourceId: 'other-feed' })]);
  const first = db.listEvents({ limit: 1, sourceId: 'fleet-feed' });
  assert.equal(first.items.length, 1); assert.equal(first.nextCursor, first.items[0].cursor);
  const second = db.listEvents({ after: first.nextCursor, limit: 1, sourceId: 'fleet-feed' });
  assert.equal(second.items.length, 1); assert.equal(second.nextCursor, null);
  assert.equal(db.pending({}).length, 3);
});
test('latest state reports expiry using current clock without changing history', (t) => {
  let clock = NOW; const db = store(t, { now: () => clock }); const input = event(); db.acceptBatch([input]);
  assert.equal(db.listState({}).items[0].freshness, 'current');
  clock += 60000; assert.equal(db.listState({}).items[0].freshness, 'expired');
  assert.equal(db.getEvent(input.eventId).disposition, 'current');
});
test('outbox acknowledgement updates delivery state only after explicit mark', (t) => {
  const db = store(t); const input = event(); const [result] = db.acceptBatch([input]);
  db.markPublished(result.cursor);
  assert.equal(db.getEvent(input.eventId).delivery, 'published'); assert.equal(db.pending({}).length, 0);
  assert.equal(db.listOutbox({ status: 'published' }).items.length, 1);
});
test('delivery retries are delayed, terminal failure is retained, admin retry is audited', (t) => {
  let clock = NOW; const db = store(t, { now: () => clock }); const input = event(); const [receipt] = db.acceptBatch([input]);
  const failure = { maxAttempts: 2, baseDelayMs: 100, maxDelayMs: 1000, code: 'PUBLISH_FAILED' };
  db.markFailed(receipt.cursor, failure); assert.equal(db.pending({}).length, 0);
  clock += 100; assert.equal(db.pending({}).length, 1);
  db.markFailed(receipt.cursor, failure); assert.equal(db.getEvent(input.eventId).delivery, 'dead');
  assert.equal(db.pending({}).length, 0); assert.equal(db.metrics().audits, 0);
  db.retryDead(input.eventId); assert.equal(db.pending({}).length, 1); assert.equal(db.metrics().audits, 1);
});
test('only dead work can be retried', (t) => {
  const db = store(t); const input = event(); db.acceptBatch([input]);
  assert.throws(() => db.retryDead(input.eventId), { code: 'OUTBOX_NOT_DEAD' });
  assert.throws(() => db.retryDead(randomUUID()), { status: 404 });
});
test('retention preserves latest state and queued/dead work while purging old settled history', (t) => {
  let clock = NOW; const db = store(t, { now: () => clock });
  const first = event(); const [r1] = db.acceptBatch([first]); db.markPublished(r1.cursor);
  const second = event({ sequence: 2 }); const [r2] = db.acceptBatch([second]);
  const stale = event({ sequence: 1 }); db.acceptBatch([stale]);
  clock += 100000;
  assert.equal(db.purge({ before: clock - 1000, limit: 100 }).deleted, 2);
  assert.equal(db.getEvent(first.eventId), null); assert.equal(db.getEvent(stale.eventId), null);
  assert.equal(db.getEvent(second.eventId).delivery, 'queued');
  db.markFailed(r2.cursor, { maxAttempts: 1, baseDelayMs: 1, maxDelayMs: 1, code: 'PUBLISH_FAILED' });
  assert.equal(db.purge({ before: clock, limit: 100 }).deleted, 0);
});
test('history and queued delivery survive a database close and restart', (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'logistics-store-'));
  let second;
  t.after(() => { second?.close(); rmSync(dir, { recursive: true, force: true }); });
  const path = join(dir, 'events.sqlite');
  const input = event(); const first = new EventStore({ path, now: () => NOW, maxPending: 10 });
  first.acceptBatch([input]); first.close();
  second = new EventStore({ path, now: () => NOW, maxPending: 10 });
  assert.equal(second.getEvent(input.eventId).event.eventId, input.eventId);
  assert.equal(second.pending({}).length, 1); assert.equal(second.listState({}).items.length, 1);
});
