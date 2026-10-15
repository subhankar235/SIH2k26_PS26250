import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createReliefWorld, advanceReliefWorld, reliefEvents, RELIEF_PHASES } from '../src/planning/world.js';
import { EVENT_TYPES } from '../src/contracts/events.js';
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
test('full run IDs isolate streams and cargo/aircraft airport references resolve to mirrored airports', () => {
  const first = createReliefWorld({ runId: 'aaaaaaaa-1111-4111-8111-111111111111', now });
  const second = createReliefWorld({ runId: 'aaaaaaaa-2222-4222-8222-222222222222', now });
  const left = reliefEvents(first, sources, now), right = reliefEvents(second, sources, now);
  assert.notEqual(left[0].entityId, right[0].entityId);
  const airports = new Set(left.filter((e) => e.type === 'airport.capacity').map((e) => e.entityId));
  for (const event of left.filter((e) => e.type === 'aircraft.status')) assert.ok(airports.has(event.data.airportId));
  for (const event of left.filter((e) => e.type === 'cargo.request')) {
    assert.ok(airports.has(event.data.originAirportId)); assert.ok(airports.has(event.data.destinationAirportId));
  }
});
