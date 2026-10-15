import { z } from 'zod';
import { createReliefWorld } from './world.js';

// The UUID namespace adds 44 characters at the gateway boundary.
const id = z.string().regex(/^SIM-[A-Za-z0-9_-]{1,16}$/);
const tick = z.number().int().min(0).max(10);
const slot = z.number().int().min(0).max(4);
const aircraft = z.strictObject({
  id, airportId: id, capacityKg: z.number().min(0).max(1_000_000), coldStorage: z.boolean(),
  status: z.enum(['available', 'maintenance', 'unavailable']), validThroughTick: tick,
});
const crew = z.strictObject({
  id, status: z.enum(['available', 'rest', 'unavailable']),
  qualifications: z.array(z.string().regex(/^[a-z][a-z-]{0,63}$/)).min(1).max(8)
    .refine(values => new Set(values).size === values.length, 'Qualifications must be unique'),
  fromSlot: slot, toSlot: slot, validThroughTick: tick,
}).superRefine((value, ctx) => {
  if (value.toSlot <= value.fromSlot) ctx.addIssue({ code: 'custom', path: ['toSlot'], message: 'Duty must end after it starts' });
});
const airport = z.strictObject({
  id, status: z.enum(['open', 'restricted', 'closed']),
  arrivalsPerSlot: z.number().int().min(0).max(3), departuresPerSlot: z.number().int().min(0).max(3), validThroughTick: tick,
}).superRefine((value, ctx) => {
  for (const field of ['arrivalsPerSlot', 'departuresPerSlot']) {
    if (value.status === 'closed' && value[field] !== 0) ctx.addIssue({ code: 'custom', path: [field], message: 'Closed airports require zero capacity' });
  }
});
const weather = z.strictObject({
  airportId: id, windSpeedMps: z.number().min(0).max(150), visibilityM: z.number().min(0).max(100_000),
  condition: z.enum(['clear', 'rain', 'fog', 'snow', 'storm']), validThroughTick: tick,
});
const route = z.strictObject({ originId: id, destinationId: id, durationSlots: z.literal(1) });
const request = z.strictObject({
  id, category: z.enum(['medical', 'food', 'water', 'equipment']), massKg: z.number().positive().max(1_000_000),
  originId: id, destinationId: id, temperatureControlled: z.boolean(), priority: z.number().int().min(1).max(5),
  deadlineSlot: z.number().int().min(1).max(4), validThroughTick: tick,
});

export const configurationSchema = z.strictObject({
  aircraft: z.array(aircraft).max(3), crews: z.array(crew).max(3), airports: z.array(airport).max(3),
  weather: z.array(weather).max(3), routes: z.array(route).max(2), requests: z.array(request).max(5),
  demandHistory: z.array(z.strictObject({ day: z.number().int().min(0).max(1_000_000), demand: z.number().int().min(0).max(1_000_000) })).max(31).optional(),
}).superRefine((configuration, ctx) => {
  const issue = (path, message) => ctx.addIssue({ code: 'custom', path, message });
  if (['aircraft', 'crews', 'airports', 'weather', 'requests'].every(key => !configuration[key].length)) issue([], 'Scenario requires at least one fictional entity');
  const ids = new Set();
  for (const key of ['aircraft', 'crews', 'airports', 'requests']) {
    configuration[key].forEach((entity, index) => {
      if (ids.has(entity.id)) issue([key, index, 'id'], 'Entity IDs must be globally unique');
      ids.add(entity.id);
    });
  }
  const airportIds = new Set(configuration.airports.map(value => value.id));
  const reference = (value, path) => { if (!airportIds.has(value)) issue(path, 'Airport reference must resolve'); };
  configuration.aircraft.forEach((value, index) => reference(value.airportId, ['aircraft', index, 'airportId']));
  const weatherIds = new Set();
  configuration.weather.forEach((value, index) => {
    reference(value.airportId, ['weather', index, 'airportId']);
    if (weatherIds.has(value.airportId)) issue(['weather', index, 'airportId'], 'Weather airport must be unique');
    weatherIds.add(value.airportId);
  });
  const routeKeys = new Set();
  for (const key of ['routes', 'requests']) configuration[key].forEach((value, index) => {
    reference(value.originId, [key, index, 'originId']); reference(value.destinationId, [key, index, 'destinationId']);
    if (value.originId === value.destinationId) issue([key, index, 'destinationId'], 'Destination must differ from origin');
    const pair = `${value.originId}|${value.destinationId}`;
    if (key === 'routes') {
      if (routeKeys.has(pair)) issue([key, index], 'Route must be unique');
      routeKeys.add(pair);
    } else if (!routeKeys.has(pair)) issue([key, index], 'Request route must resolve');
  });
  configuration.airports.forEach((value, index) => {
    if (!weatherIds.has(value.id)) issue(['airports', index], 'Airport requires weather evidence');
    if (value.status !== 'closed' && !configuration.routes.some(route => route.originId === value.id || route.destinationId === value.id)) {
      issue(['airports', index], 'Usable airport requires a scenario route');
    }
  });
  const days = new Set();
  configuration.demandHistory?.forEach((value, index) => {
    if (days.has(value.day)) issue(['demandHistory', index, 'day'], 'History days must be unique');
    days.add(value.day);
  });
});

export function configuredReliefWorld(configuration, { runId, now = Date.now() } = {}) {
  const parsed = configurationSchema.parse(configuration);
  if (runId !== undefined && (typeof runId !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(runId))) {
    throw new TypeError('Invalid fictional run ID');
  }
  if (typeof now !== 'number' || !Number.isFinite(now) || !Number.isFinite(new Date(now).getTime())) throw new TypeError('Invalid run timestamp');
  const base = createReliefWorld({ runId, now });
  return { ...base, ...parsed, demandHistory: parsed.demandHistory ?? base.demandHistory };
}
