import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildScenario } from '../src/scenario.js';
import { EVENT_TYPES, validateEvent } from '../src/contracts.js';
import { EventStore } from '../src/store.js';
import { monitoringSnapshot } from '../src/monitoring.js';
const NOW = Date.parse('2026-10-15T06:00:00Z');
const sources = EVENT_TYPES.map((type) => ({ sourceId: type.split('.')[0], types: [type] }));

test('finite scenario demonstrates changes, gaps, duplicate, stale and TTL without scheduling', (t) => {
  let clock = NOW; const store = new EventStore({ path: ':memory:', now: () => clock }); t.after(() => store.close());
  const scenario = buildScenario({ sources, now: NOW, intervalMs: 100, runId: 'unit' });
  const dispositions = [];
  for (const step of scenario.steps) {
    clock += step.delayMs;
    for (const input of step.events) {
      const normalized = validateEvent(input, { now: clock });
      dispositions.push(...store.acceptBatch([normalized]));
    }
  }
  assert.equal(clock - NOW, 700); assert.equal(dispositions.filter((r) => r.duplicate).length, 1);
  assert.equal(dispositions.filter((r) => r.disposition === 'stale').length, 1);
  const snapshot = monitoringSnapshot(store, {}, clock);
  assert.equal(snapshot.records.length, 5); assert.equal(snapshot.summary.sequenceGaps, 1);
  assert.equal(snapshot.summary.expired, 1);
  assert.equal(snapshot.records.find((r) => r.event.type === 'airport.capacity').reportedStatus, 'closed');
  assert.equal(snapshot.records.find((r) => r.event.type === 'aircraft.status').reportedStatus, 'maintenance');
  assert.equal(snapshot.records.find((r) => r.event.type === 'weather.observation').reportedStatus, 'rain');
});

test('scenario refuses missing source permissions or unsafe timing/id bounds', () => {
  assert.throws(() => buildScenario({ sources: [], now: NOW }));
  for (const intervalMs of [0, -1, 99, 10001, 1.5]) assert.throws(() => buildScenario({ sources, intervalMs }));
  assert.throws(() => buildScenario({ sources, runId: '../secret' }));
});
