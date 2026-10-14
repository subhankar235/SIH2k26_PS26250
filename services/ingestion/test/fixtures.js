import { randomUUID } from 'node:crypto';

// Merge data overrides into the defaults for the selected type. Invalid values
// remain intact so callers can exercise validation failures deliberately.
export function event(overrides = {}, now = Date.now()) {
  const stamp = (offset) => new Date(now + offset).toISOString();
  const type = overrides.type ?? 'aircraft.status';
  const data = {
    'aircraft.status': { status: 'available', airportId: 'airport-1', capacityKg: 5000 },
    'crew.availability': {
      status: 'available', qualifications: ['maintenance'],
      availableFrom: stamp(0), availableUntil: stamp(3_600_000),
    },
    'weather.observation': {
      temperatureC: 20, windSpeedMps: 4, visibilityM: 10000, condition: 'clear',
    },
    'airport.capacity': { status: 'open', arrivalsPerHour: 10, departuresPerHour: 10 },
    'cargo.request': {
      category: 'food', massKg: 1000, originAirportId: 'airport-1',
      destinationAirportId: 'airport-2', requestedDeliveryBy: stamp(3_600_000),
      temperatureControlled: false,
    },
  }[type];
  return {
    schemaVersion: 1, eventId: randomUUID(), sourceId: 'source-1', type,
    entityId: 'entity-1', sequence: 1, observedAt: stamp(0), validUntil: stamp(3_600_000),
    ...overrides,
    data: Object.hasOwn(overrides, 'data') &&
      (overrides.data === null || typeof overrides.data !== 'object' || Array.isArray(overrides.data))
      ? overrides.data : { ...data, ...overrides.data },
  };
}
