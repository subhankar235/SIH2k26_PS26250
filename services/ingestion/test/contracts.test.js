import assert from 'node:assert/strict';
import { test } from 'node:test';
import { z } from 'zod';
import { EVENT_TYPES, TOPICS, eventSchema, validateEvent, canonicalJson, eventSchemas } from '../src/contracts.js';
import { ApiError } from '../src/errors.js';
import { event } from './fixtures.js';

const now = Date.parse('2026-10-15T12:00:00Z');
const validate = (input) => validateEvent(input, { now });
function rejects(input, path) {
  assert.throws(() => validate(input), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 422);
    assert.equal(error.code, 'VALIDATION_ERROR');
    assert.ok(error.details.some((issue) => issue.path === path || issue.path.startsWith(`${path}.`)), JSON.stringify(error.details));
    return true;
  });
}

test('publishes frozen event types and server-owned topic mapping', () => {
  assert.deepEqual(EVENT_TYPES, ['aircraft.status', 'crew.availability', 'weather.observation', 'airport.capacity', 'cargo.request']);
  assert.deepEqual(TOPICS, {
    'aircraft.status': 'logistics.aircraft.v1', 'crew.availability': 'logistics.crew.v1',
    'weather.observation': 'logistics.weather.v1', 'airport.capacity': 'logistics.airport.v1',
    'cargo.request': 'logistics.cargo.v1',
  });
  assert.ok(Object.isFrozen(EVENT_TYPES));
  assert.ok(Object.isFrozen(TOPICS));
});

test('accepts each domain and returns a new parsed value without mutating input', () => {
  for (const type of EVENT_TYPES) {
    const input = event({ type }, now);
    assert.deepEqual(validate(input), input);
    assert.notEqual(validate(input), input);
    assert.equal(eventSchema.safeParse(input).success, true);
  }
});

test('ApiError exposes the HTTP error contract', () => {
  const details = [{ path: 'sequence', message: 'Invalid sequence' }];
  const error = new ApiError(422, 'VALIDATION_ERROR', 'Invalid event', details);
  assert.ok(error instanceof Error);
  assert.equal(error.status, 422);
  assert.equal(error.code, 'VALIDATION_ERROR');
  assert.equal(error.message, 'Invalid event');
  assert.equal(error.details, details);
});

test('normalizes UTC and offset timestamps in every domain timestamp field', () => {
  const offset = '2026-10-15T17:30:00+05:30';
  const offsetLater = '2026-10-15T18:30:00+05:30';
  for (const type of EVENT_TYPES) {
    const data = type === 'aircraft.status' ? { maintenanceDueAt: offsetLater }
      : type === 'crew.availability' ? { availableFrom: offset, availableUntil: offsetLater }
        : type === 'cargo.request' ? { requestedDeliveryBy: offsetLater } : {};
    const input = event({ type, observedAt: offset, validUntil: offsetLater, data }, now);
    const parsed = validate(input);
    assert.equal(parsed.observedAt, '2026-10-15T12:00:00.000Z');
    assert.equal(parsed.validUntil, '2026-10-15T13:00:00.000Z');
    for (const [field, timestamp] of Object.entries(data)) {
      assert.equal(parsed.data[field], new Date(timestamp).toISOString());
    }
    assert.equal(input.observedAt, offset);
  }
});

test('rejects invalid calendar dates, missing timezone, malformed offsets, and missing seconds', () => {
  for (const observedAt of ['2026-02-29T12:00:00Z', '2026-04-31T12:00:00Z',
    '2026-10-15T12:00:00', '2026-10-15T12:00Z', '2026-10-15T12:00:00+24:00',
    '2026-10-15T12:00:00+05:60', '2026-10-15T24:00:00Z', 'garbage']) {
    rejects(event({ observedAt }, now), 'observedAt');
  }
  assert.equal(validate(event({ observedAt: '2024-02-29T12:00:00Z', validUntil: '2024-02-29T13:00:00Z' }, now)).observedAt,
    '2024-02-29T12:00:00.000Z');
});

test('bounds validity duration and future observations using the injected epoch clock', () => {
  for (const delta of [0, -1, 7 * 86_400_000 + 1]) {
    rejects(event({ validUntil: new Date(now + delta).toISOString() }, now), 'validUntil');
  }
  assert.ok(validate(event({ validUntil: new Date(now + 7 * 86_400_000).toISOString() }, now)));
  assert.ok(validate(event({}, now + 60_000)));
  rejects(event({}, now + 60_001), 'observedAt');
  assert.ok(validate(event({}, now - 86_400_000)), 'Expired history remains ingestible');
});

test('rejects unknown fields on the envelope and every data object', () => {
  rejects(event({ topic: 'client-owned' }, now), '');
  for (const type of EVENT_TYPES) rejects(event({ type, data: { extra: true } }, now), 'data');
});

test('requires exact envelope literals, UUID and identifier grammar', () => {
  for (const [field, values] of Object.entries({
    schemaVersion: [0, '1', 2], eventId: ['not-a-uuid'], type: ['unknown', 'aircraft'],
    sourceId: ['', '_source', 'space id', 'source\n', 'a'.repeat(65)], entityId: ['', '-entity', 'a/b'],
  })) for (const value of values) rejects(event({ [field]: value }, now), field);
  for (const field of ['eventId', 'sourceId', 'type', 'entityId', 'schemaVersion', 'observedAt', 'validUntil', 'data']) {
    const input = event({}, now);
    delete input[field];
    rejects(input, field);
  }
  assert.ok(validate(event({ sourceId: 'A._-9', entityId: 'a'.repeat(64) }, now)));
});

test('requires a positive safe integer sequence without coercion', () => {
  for (const sequence of [0, -1, 1.1, Number.MAX_SAFE_INTEGER + 1, Infinity, NaN, '1']) {
    rejects(event({ sequence }, now), 'sequence');
  }
  assert.equal(validate(event({ sequence: Number.MAX_SAFE_INTEGER }, now)).sequence, Number.MAX_SAFE_INTEGER);
});

test('bounds finite aircraft capacity and validates its airport and maintenance timestamp', () => {
  for (const capacityKg of [-1, 1_000_001, Infinity, -Infinity, NaN, '12']) rejects(event({ data: { capacityKg } }, now), 'data.capacityKg');
  for (const capacityKg of [0, 1_000_000]) assert.ok(validate(event({ data: { capacityKg } }, now)));
  rejects(event({ data: { airportId: '_airport' } }, now), 'data.airportId');
  rejects(event({ data: { maintenanceDueAt: '2026-02-30T00:00:00Z' } }, now), 'data.maintenanceDueAt');
  rejects(event({ data: { status: 'flying' } }, now), 'data.status');
});

test('requires bounded unique crew qualifications and an increasing availability range', () => {
  for (const qualifications of [[], ['a', 'a'], Array.from({ length: 17 }, (_, i) => `q${i}`), ['bad id']]) {
    rejects(event({ type: 'crew.availability', data: { qualifications } }, now), 'data.qualifications');
  }
  for (const availableUntil of ['2026-10-15T12:00:00Z', '2026-10-15T11:00:00Z']) {
    rejects(event({ type: 'crew.availability', data: { availableUntil } }, now), 'data.availableUntil');
  }
  assert.ok(validate(event({ type: 'crew.availability', data: { qualifications: Array.from({ length: 16 }, (_, i) => `q${i}`) } }, now)));
  rejects(event({ type: 'crew.availability', data: { status: 'unknown' } }, now), 'data.status');
});

test('bounds weather measurements and requires a known condition', () => {
  for (const [field, values] of Object.entries({ temperatureC: [-101, 61, NaN], windSpeedMps: [-1, 151, Infinity], visibilityM: [-1, 100_001, Infinity] })) {
    for (const value of values) rejects(event({ type: 'weather.observation', data: { [field]: value } }, now), `data.${field}`);
  }
  for (const data of [{ temperatureC: -100, windSpeedMps: 0, visibilityM: 0 }, { temperatureC: 60, windSpeedMps: 150, visibilityM: 100_000 }]) {
    assert.ok(validate(event({ type: 'weather.observation', data }, now)));
  }
  rejects(event({ type: 'weather.observation', data: { condition: 'sunny' } }, now), 'data.condition');
});

test('requires bounded integer airport capacity and zero traffic when closed', () => {
  for (const field of ['arrivalsPerHour', 'departuresPerHour']) {
    for (const value of [-1, 1001, 0.5, Infinity]) rejects(event({ type: 'airport.capacity', data: { [field]: value } }, now), `data.${field}`);
    rejects(event({ type: 'airport.capacity', data: { status: 'closed', arrivalsPerHour: 0, departuresPerHour: 0, [field]: 1 } }, now), `data.${field}`);
  }
  assert.ok(validate(event({ type: 'airport.capacity', data: { status: 'closed', arrivalsPerHour: 0, departuresPerHour: 0 } }, now)));
  rejects(event({ type: 'airport.capacity', data: { status: 'unknown' } }, now), 'data.status');
});

test('requires ordinary cargo with positive finite mass and distinct airports', () => {
  for (const massKg of [0, -1, 1_000_001, Infinity, NaN]) rejects(event({ type: 'cargo.request', data: { massKg } }, now), 'data.massKg');
  assert.ok(validate(event({ type: 'cargo.request', data: { massKg: 1_000_000 } }, now)));
  rejects(event({ type: 'cargo.request', data: { destinationAirportId: 'airport-1' } }, now), 'data.destinationAirportId');
  rejects(event({ type: 'cargo.request', data: { category: 'weapons' } }, now), 'data.category');
  rejects(event({ type: 'cargo.request', data: { temperatureControlled: 'false' } }, now), 'data.temperatureControlled');
  rejects(event({ type: 'cargo.request', data: { requestedDeliveryBy: 'tomorrow' } }, now), 'data.requestedDeliveryBy');
});

test('bounds validation issue counts and text without reflecting submitted values', () => {
  const secret = 'sensitive-input-'.repeat(1000);
  assert.throws(() => validate(event({ data: { [secret]: secret, status: secret } }, now)), (error) => {
    assert.ok(error.details.length <= 20);
    for (const issue of error.details) {
      assert.ok(issue.path.length <= 128);
      assert.ok(issue.message.length <= 160);
    }
    assert.ok(!JSON.stringify(error.details).includes('sensitive-input-'));
    return true;
  });
  const invalidCrew = event({ type: 'crew.availability', data: { qualifications: Array(100).fill('bad id') } }, now);
  assert.throws(() => validate(invalidCrew), (error) => error.details.length <= 20);
});

test('canonical JSON recursively sorts object keys and preserves array order', () => {
  assert.equal(canonicalJson({ b: [2, { z: 1, a: 3 }], a: true }), '{"a":true,"b":[2,{"a":3,"z":1}]}');
  assert.equal(canonicalJson({ b: 2, a: 1 }), canonicalJson({ a: 1, b: 2 }));
  assert.notEqual(canonicalJson([1, 2]), canonicalJson([2, 1]));
  assert.equal(canonicalJson(JSON.parse('{"__proto__":{"z":1},"a":2}')), '{"__proto__":{"z":1},"a":2}');
});

test('canonical JSON rejects values that would silently lose information', () => {
  for (const value of [Infinity, NaN, undefined, { a: undefined }, [undefined], 1n]) {
    assert.throws(() => canonicalJson(value), TypeError);
  }
});

test('exports input JSON schemas generated from the same event schema branches', () => {
  const schemas = eventSchemas();
  assert.deepEqual(Object.keys(schemas), EVENT_TYPES);
  for (const [index, type] of EVENT_TYPES.entries()) {
    assert.deepEqual(schemas[type], z.toJSONSchema(eventSchema.options[index], { io: 'input' }));
    assert.equal(schemas[type].additionalProperties, false);
    assert.equal(schemas[type].properties.data.additionalProperties, false);
    assert.equal(schemas[type].properties.type.const, type);
    assert.equal(schemas[type].properties.observedAt.format, 'date-time');
  }
});
