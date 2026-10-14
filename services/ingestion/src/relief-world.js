import { randomUUID } from 'node:crypto';
import { EVENT_TYPES, validateEvent } from './contracts.js';

export const RELIEF_PHASES = Object.freeze(['weather-change', 'maintenance-change', 'airport-closure', 'new-request', 'validity-expiry']);
export function createReliefWorld({ runId = randomUUID(), now = Date.now() } = {}) {
  return { version: 1, simulation: true, runId, revision: 0, tick: 0, createdAt: new Date(now).toISOString(),
    policy: { slots: [0, 1, 2], slotMinutes: 30, minVisibilityM: 3000, maxWindSpeedMps: 15 },
    aircraft: [
      { id: 'SIM-A1', airportId: 'SIM-HUB', capacityKg: 800, coldStorage: true, status: 'available', validThroughTick: 5 },
      { id: 'SIM-A2', airportId: 'SIM-HUB', capacityKg: 1200, coldStorage: false, status: 'available', validThroughTick: 5 },
      { id: 'SIM-A3', airportId: 'SIM-HUB', capacityKg: 600, coldStorage: true, status: 'available', validThroughTick: 5 },
    ],
    crews: ['SIM-C1', 'SIM-C2', 'SIM-C3'].map((id, i) => ({ id, status: i === 2 ? 'rest' : 'available', qualifications: ['relief-pilot'], fromSlot: 0, toSlot: 4, validThroughTick: 5 })),
    airports: ['SIM-HUB', 'SIM-CLINIC', 'SIM-SHELTER'].map((id) => ({ id, status: 'open', arrivalsPerSlot: 2, departuresPerSlot: 2, validThroughTick: 5 })),
    weather: ['SIM-HUB', 'SIM-CLINIC', 'SIM-SHELTER'].map((airportId) => ({ airportId, windSpeedMps: 5, visibilityM: 10000, condition: 'clear', validThroughTick: 5 })),
    routes: ['SIM-CLINIC', 'SIM-SHELTER'].map((destinationId) => ({ originId: 'SIM-HUB', destinationId, durationSlots: 1 })),
    requests: [
      { id: 'SIM-REQ-MED', category: 'medical', massKg: 600, originId: 'SIM-HUB', destinationId: 'SIM-CLINIC', temperatureControlled: true, priority: 5, deadlineSlot: 2, validThroughTick: 5 },
      { id: 'SIM-REQ-WATER', category: 'water', massKg: 700, originId: 'SIM-HUB', destinationId: 'SIM-SHELTER', temperatureControlled: false, priority: 4, deadlineSlot: 3, validThroughTick: 5 },
      { id: 'SIM-REQ-FOOD', category: 'food', massKg: 300, originId: 'SIM-HUB', destinationId: 'SIM-SHELTER', temperatureControlled: false, priority: 3, deadlineSlot: 3, validThroughTick: 5 },
      { id: 'SIM-REQ-EQUIP', category: 'equipment', massKg: 500, originId: 'SIM-HUB', destinationId: 'SIM-CLINIC', temperatureControlled: false, priority: 1, deadlineSlot: 4, validThroughTick: 5 },
    ], demandHistory: Array.from({ length: 31 }, (_, day) => ({ day, demand: 2 + day % 7 })),
  };
}

export function advanceReliefWorld(previous, phase) {
  if (phase !== RELIEF_PHASES[previous.revision]) throw new Error('Unexpected relief phase.');
  const world = structuredClone(previous); world.revision++; world.tick++;
  if (phase === 'weather-change') Object.assign(world.weather.find((w) => w.airportId === 'SIM-CLINIC'), { condition: 'storm', windSpeedMps: 25, visibilityM: 1500 });
  if (phase === 'maintenance-change') world.aircraft[0].status = 'maintenance';
  if (phase === 'airport-closure') Object.assign(world.airports.find((a) => a.id === 'SIM-SHELTER'), { status: 'closed', arrivalsPerSlot: 0, departuresPerSlot: 0 });
  if (phase === 'new-request') {
    Object.assign(world.weather.find((w) => w.airportId === 'SIM-CLINIC'), { condition: 'clear', windSpeedMps: 5, visibilityM: 10000 });
    Object.assign(world.airports.find((a) => a.id === 'SIM-SHELTER'), { status: 'restricted', arrivalsPerSlot: 1, departuresPerSlot: 1 });
    world.requests.push({ id: 'SIM-REQ-NEW', category: 'water', massKg: 100, originId: 'SIM-HUB', destinationId: 'SIM-SHELTER', temperatureControlled: false, priority: 5, deadlineSlot: 1, validThroughTick: 5 });
  }
  if (phase === 'validity-expiry') world.tick = 6;
  return world;
}

/** Mirror ordinary fixture facts; toy policy/priority/cold storage stay scenario metadata. */
export function reliefEvents(world, sources, now = Date.now()) {
  const prefix = `relief-${world.runId}-`;
  const timestamp = (minutes) => new Date(now + minutes * 60000).toISOString();
  const sourceByType = Object.fromEntries(EVENT_TYPES.map((type) => {
    const source = sources.find((s) => s.types.includes(type));
    if (!source) throw new Error(`Simulation requires a configured source for ${type}.`);
    return [type, source.sourceId];
  }));
  const slotTimestamp = (minutes) => new Date(Date.parse(world.createdAt) + minutes * 60000).toISOString();
  const make = (type, id, data) => validateEvent({ schemaVersion: 1, eventId: randomUUID(), sourceId: sourceByType[type], entityId: prefix + id,
    type, sequence: world.revision + 1, observedAt: timestamp(0), validUntil: timestamp(120), data }, { now });
  return [
    ...world.aircraft.map((a) => make('aircraft.status', a.id, { status: a.status, airportId: prefix + a.airportId, capacityKg: a.capacityKg })),
    ...world.crews.map((c) => make('crew.availability', c.id, { status: c.status, qualifications: c.qualifications, availableFrom: slotTimestamp(c.fromSlot * 30), availableUntil: slotTimestamp(c.toSlot * 30) })),
    ...world.airports.map((a) => make('airport.capacity', a.id, { status: a.status, arrivalsPerHour: a.arrivalsPerSlot * 2, departuresPerHour: a.departuresPerSlot * 2 })),
    ...world.weather.map((w) => make('weather.observation', w.airportId, { temperatureC: w.temperatureC ?? 24, windSpeedMps: w.windSpeedMps, visibilityM: w.visibilityM, condition: w.condition })),
    ...world.requests.map((r) => make('cargo.request', r.id, { category: r.category, massKg: r.massKg, originAirportId: prefix + r.originId, destinationAirportId: prefix + r.destinationId, requestedDeliveryBy: slotTimestamp(r.deadlineSlot * 30), temperatureControlled: r.temperatureControlled })),
  ];
}
