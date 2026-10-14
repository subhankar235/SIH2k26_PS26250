import assert from 'node:assert/strict';
import test from 'node:test';
import { configurationSchema, configuredReliefWorld } from '../src/relief-configuration.js';
import { createReliefWorld, reliefEvents } from '../src/relief-world.js';
import { optimizeReliefWorld, validateReliefPlan } from '../src/relief-planner.js';

const runId = '00000000-0000-4000-8000-000000000001';
function configuration() {
  const { aircraft, crews, airports, weather, routes, requests, demandHistory } = createReliefWorld({ runId, now: 0 });
  return { aircraft, crews, airports, weather, routes, requests, demandHistory };
}

test('configured fixtures preserve editable evidence while server owns identity and policy', () => {
  const input = configuration();
  input.aircraft[0].capacityKg = 950; input.requests[0].priority = 2;
  const w = configuredReliefWorld(input, { runId, now: 0 });
  assert.equal(w.runId, runId);
  assert.equal(w.createdAt, '1970-01-01T00:00:00.000Z');
  assert.equal(w.revision, 0); assert.equal(w.tick, 0); assert.equal(w.simulation, true);
  assert.deepEqual(w.policy, createReliefWorld({ runId, now: 0 }).policy);
  assert.equal(w.aircraft[0].capacityKg, 950); assert.equal(w.requests[0].priority, 2);
  input.aircraft[0].capacityKg = 1;
  assert.equal(w.aircraft[0].capacityKg, 950);
  assert.deepEqual(validateReliefPlan(w, optimizeReliefWorld(w)), { valid: true, errors: [] });
});

test('omitting demand history uses the fixed default without sharing state', () => {
  const input = configuration(); delete input.demandHistory;
  const a = configuredReliefWorld(input, { runId, now: 0 });
  const b = configuredReliefWorld(input, { runId, now: 0 });
  assert.deepEqual(a.demandHistory, createReliefWorld({ runId, now: 0 }).demandHistory);
  a.demandHistory[0].demand = 999; assert.notEqual(b.demandHistory[0].demand, 999);
});

test('configuration rejects unknown properties at each boundary, policy and military cargo', () => {
  for (const mutate of [
    c => { c.runId = runId; }, c => { c.policy = {}; }, c => { c.tools = []; },
    ...['aircraft', 'crews', 'airports', 'weather', 'routes', 'requests', 'demandHistory'].map(key => c => { c[key][0].injected = true; }),
    c => { c.requests[0].category = 'weapons'; },
  ]) {
    const input = configuration(); mutate(input);
    assert.equal(configurationSchema.safeParse(input).success, false);
    assert.throws(() => configuredReliefWorld(input, { runId, now: 0 }));
  }
});

test('configuration enforces bounded collections and finite civilian fields', () => {
  for (const mutate of [
    ...Object.entries({ aircraft: 3, crews: 3, airports: 3, weather: 3, routes: 2, requests: 5, demandHistory: 31 })
      .map(([key, max]) => c => { c[key] = Array.from({ length: max + 1 }, () => structuredClone(c[key][0])); }),
    c => { c.aircraft[0].capacityKg = Infinity; }, c => { c.requests[0].massKg = 0; },
    c => { c.requests[0].priority = 6; }, c => { c.routes[0].durationSlots = 2; },
    c => { c.crews[0].fromSlot = 4; c.crews[0].toSlot = 1; },
    c => { c.airports[0].departuresPerSlot = 4; }, c => { c.airports[0].status = 'closed'; },
    c => { c.weather[0].condition = 'unknown'; }, c => { c.weather[0].windSpeedMps = 151; },
    c => { c.weather[0].visibilityM = 100001; },
    c => { c.crews[0].qualifications = ['relief-pilot', 'relief-pilot']; },
    c => { c.crews[0].qualifications = ['X'.repeat(80)]; },
    c => { c.requests[0].validThroughTick = 11; }, c => { c.demandHistory[1].day = 0; },
  ]) {
    const input = configuration(); mutate(input);
    assert.equal(configurationSchema.safeParse(input).success, false);
  }
});

test('identifiers and references resolve and use SIM IDs no longer than twenty characters', () => {
  for (const mutate of [
    c => { c.aircraft[0].id = 'REAL-A1'; }, c => { c.aircraft[0].id = 'SIM-' + 'A'.repeat(17); },
    c => { c.aircraft[0].airportId = 'SIM-MISSING'; }, c => { c.weather[0].airportId = 'SIM-MISSING'; },
    c => { c.routes[0].destinationId = 'SIM-MISSING'; }, c => { c.requests[0].originId = 'SIM-MISSING'; },
    c => { c.requests[0].destinationId = c.requests[0].originId; },
    c => { c.crews[0].id = c.aircraft[0].id; }, c => { c.weather[1].airportId = c.weather[0].airportId; },
    c => { c.routes[1] = structuredClone(c.routes[0]); }, c => { c.weather.pop(); }, c => { c.routes.pop(); },
  ]) {
    const input = configuration(); mutate(input);
    assert.equal(configurationSchema.safeParse(input).success, false);
  }
  const input = configuration(); input.aircraft[0].id = 'SIM-' + 'A'.repeat(16);
  const w = configuredReliefWorld(input, { runId, now: 0 });
  const sources = ['aircraft.status', 'crew.availability', 'weather.observation', 'airport.capacity', 'cargo.request']
    .map(type => ({ sourceId: 'source', types: [type] }));
  assert.ok(reliefEvents(w, sources, 0).every(event => event.entityId.length <= 64));
});

test('configured worlds reject malformed trusted run metadata', () => {
  assert.throws(() => configuredReliefWorld(configuration(), { runId: 'bad', now: 0 }));
  assert.throws(() => configuredReliefWorld(configuration(), { runId, now: Infinity }));
  assert.throws(() => configuredReliefWorld(configuration(), { runId: { toString: () => runId }, now: 0 }));
});
