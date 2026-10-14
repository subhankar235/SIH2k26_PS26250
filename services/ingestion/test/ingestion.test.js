import assert from 'node:assert/strict';
import { test } from 'node:test';
import { EventStore } from '../src/store.js';
import { IngestionService } from '../src/ingestion.js';
import { event } from './fixtures.js';

const NOW = Date.parse('2026-10-15T06:00:00Z');
const source = { sourceId: 'test-source', types: ['aircraft.status'] };
function setup(t) {
  const store = new EventStore({ path: ':memory:', now: () => NOW, maxPending: 10 });
  t.after(() => store.close());
  return { store, ingestion: new IngestionService({ store, now: () => NOW }) };
}
function input(overrides = {}) { return event({ sourceId: 'test-source', ...overrides }, NOW); }

test('ingestion validates and normalizes before persisting', (t) => {
  const { store, ingestion } = setup(t);
  const raw = input({ observedAt: '2026-10-15T11:29:59+05:30' });
  const [receipt] = ingestion.accept([raw], source);
  assert.equal(store.getEvent(receipt.eventId).event.observedAt, '2026-10-15T05:59:59.000Z');
});
test('an authenticated feed cannot spoof another source', (t) => {
  const { store, ingestion } = setup(t);
  assert.throws(() => ingestion.accept([input({ sourceId: 'another-source' })], source), { status: 403 });
  assert.equal(store.metrics().events, 0);
});
test('source permissions restrict accepted event types', (t) => {
  const { store, ingestion } = setup(t);
  assert.throws(() => ingestion.accept([input({ type: 'weather.observation' })], source), { status: 403 });
  assert.equal(store.metrics().events, 0);
});
test('invalid final batch member prevents earlier valid event writes', (t) => {
  const { store, ingestion } = setup(t);
  assert.throws(() => ingestion.accept([input(), input({ injected: 'unknown-field' })], source), { status: 422 });
  assert.equal(store.metrics().events, 0);
});
test('invalid batch bounds are rejected without writes', (t) => {
  const { store, ingestion } = setup(t);
  for (const value of [[], null, {}, Array(101).fill(input())]) {
    assert.throws(() => ingestion.accept(value, source), { status: 422 });
  }
  assert.equal(store.metrics().events, 0);
});
