import { randomUUID } from 'node:crypto';

/** Fictional administrative observations; no flight assignments or tactical decisions. */
export function sampleEvent(type, { sourceId, now = Date.now(), sequence = 1, entityId } = {}) {
  const later = (milliseconds) => new Date(now + milliseconds).toISOString();
  const data = {
    'aircraft.status': { status: 'available', airportId: 'RELIEF-HUB', capacityKg: 1200 },
    'crew.availability': { status: 'available', qualifications: ['transport-qualified'], availableFrom: later(-60000), availableUntil: later(3600000) },
    'weather.observation': { temperatureC: 24, windSpeedMps: 4, visibilityM: 10000, condition: 'clear' },
    'airport.capacity': { status: 'open', arrivalsPerHour: 12, departuresPerHour: 12 },
    'cargo.request': { category: 'medical', massKg: 250, originAirportId: 'RELIEF-HUB', destinationAirportId: 'RELIEF-OUTPOST', requestedDeliveryBy: later(3600000), temperatureControlled: true },
  }[type];
  if (!data) throw new Error('Unknown sample event type.');
  return { schemaVersion: 1, eventId: randomUUID(), sourceId: sourceId ?? `demo-${type.split('.')[0]}`,
    type, entityId: entityId ?? `${type.split('.')[0]}-demo`, sequence,
    observedAt: later(0), validUntil: later(120000), data };
}
