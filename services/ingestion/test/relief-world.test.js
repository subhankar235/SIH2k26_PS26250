import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createReliefWorld, advanceReliefWorld, reliefEvents, RELIEF_PHASES } from '../src/relief-world.js';
import { EVENT_TYPES } from '../src/contracts.js';
const now = Date.parse('2026-10-15T06:00:00Z');
const sources = EVENT_TYPES.map((type) => ({ sourceId: `relief-${type.split('.')[0]}`, types: [type] }));
test('fixed civilian world is sealed to finite ordinary cargo and validated gateway fixtures', () => {
  const world = createReliefWorld({ now });
  assert.equal(world.simulation, true); assert.equal(world.requests.length, 4);
  assert.equal(reliefEvents(world, sources, now).length, 16);
  assert.throws(() => reliefEvents(world, sources.slice(1), now));
  assert.throws(() => advanceReliefWorld(world, 'airport-closure'));
  let latest = world;
  for (const phase of RELIEF_PHASES) {
    const next = advanceReliefWorld(latest, phase); assert.notEqual(next, latest);
    assert.equal(next.revision, latest.revision + 1); reliefEvents(next, sources, now); latest = next;
  }
  assert.equal(world.tick, 0); assert.equal(latest.tick, 6); assert.equal(latest.requests.length, 5);
  assert.ok(latest.aircraft.every((a) => a.validThroughTick < latest.tick));
});
