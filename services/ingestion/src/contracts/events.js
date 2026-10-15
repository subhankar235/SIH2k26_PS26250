import { z } from 'zod';
import { ApiError } from '../platform/errors.js';

export const TOPICS = Object.freeze({
  'aircraft.status': 'logistics.aircraft.v1',
  'crew.availability': 'logistics.crew.v1',
  'weather.observation': 'logistics.weather.v1',
  'airport.capacity': 'logistics.airport.v1',
  'cargo.request': 'logistics.cargo.v1',
});
export const EVENT_TYPES = Object.freeze(Object.keys(TOPICS));

const identifier = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/);
// Zod's datetime check validates calendar dates as well as timezone syntax.
const timestamp = z.iso.datetime({ offset: true })
  .transform((value) => new Date(value).toISOString());
const envelope = {
  schemaVersion: z.literal(1), eventId: z.uuid(), sourceId: identifier,
  entityId: identifier, sequence: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
  observedAt: timestamp, validUntil: timestamp,
};

const dataSchemas = {
  'aircraft.status': z.strictObject({
    status: z.enum(['available', 'maintenance', 'unavailable']),
    airportId: identifier, capacityKg: z.number().min(0).max(1_000_000),
    maintenanceDueAt: timestamp.optional(),
  }),
  'crew.availability': z.strictObject({
    status: z.enum(['available', 'unavailable', 'rest']),
    qualifications: z.array(identifier).min(1).max(16)
      .refine((values) => new Set(values).size === values.length, 'Qualifications must be unique'),
    availableFrom: timestamp, availableUntil: timestamp,
  }).superRefine((data, ctx) => {
    if (Date.parse(data.availableUntil) <= Date.parse(data.availableFrom)) {
      ctx.addIssue({ code: 'custom', path: ['availableUntil'], message: 'Availability must end after it starts' });
    }
  }),
  'weather.observation': z.strictObject({
    temperatureC: z.number().min(-100).max(60), windSpeedMps: z.number().min(0).max(150),
    visibilityM: z.number().min(0).max(100_000), condition: z.enum(['clear', 'rain', 'fog', 'snow', 'storm']),
  }),
  'airport.capacity': z.strictObject({
    status: z.enum(['open', 'restricted', 'closed']),
    arrivalsPerHour: z.number().int().min(0).max(1000),
    departuresPerHour: z.number().int().min(0).max(1000),
  }).superRefine((data, ctx) => {
    if (data.status === 'closed') {
      for (const field of ['arrivalsPerHour', 'departuresPerHour']) {
        if (data[field] !== 0) ctx.addIssue({ code: 'custom', path: [field], message: 'Closed airports require zero capacity' });
      }
    }
  }),
  'cargo.request': z.strictObject({
    category: z.enum(['medical', 'food', 'water', 'equipment']),
    massKg: z.number().positive().max(1_000_000), originAirportId: identifier,
    destinationAirportId: identifier, requestedDeliveryBy: timestamp, temperatureControlled: z.boolean(),
  }).superRefine((data, ctx) => {
    if (data.originAirportId === data.destinationAirportId) {
      ctx.addIssue({ code: 'custom', path: ['destinationAirportId'], message: 'Destination must differ from origin' });
    }
  }),
};

const schemas = Object.fromEntries(EVENT_TYPES.map((type) => [type,
  z.strictObject({ ...envelope, type: z.literal(type), data: dataSchemas[type] })
    .superRefine((event, ctx) => {
      const duration = Date.parse(event.validUntil) - Date.parse(event.observedAt);
      if (duration <= 0 || duration > 7 * 86_400_000) {
        ctx.addIssue({ code: 'custom', path: ['validUntil'], message: 'Validity must end after observation and within seven days' });
      }
    }),
]));
export const eventSchema = z.discriminatedUnion('type', Object.values(schemas));

function validationError(issues) {
  const details = issues.slice(0, 20).map((issue) => ({
    path: issue.path.join('.').slice(0, 128),
    // Unknown property names are untrusted and must not appear in error messages.
    message: (issue.code === 'unrecognized_keys' ? 'Unknown fields are not permitted' : issue.message).slice(0, 160),
  }));
  return new ApiError(422, 'VALIDATION_ERROR', 'Event validation failed', details);
}

export function validateEvent(input, { now = Date.now() } = {}) {
  if (typeof now !== 'number' || !Number.isFinite(now)) throw new TypeError('now must be finite epoch milliseconds');
  const result = eventSchema.safeParse(input);
  if (!result.success) throw validationError(result.error.issues);
  if (Date.parse(result.data.observedAt) > now + 60_000) {
    throw validationError([{ path: ['observedAt'], message: 'Observation cannot be over sixty seconds in the future' }]);
  }
  return result.data;
}

// Canonical serialization is for JSON values; reject unsupported inputs rather
// than silently omitting fields or turning nonfinite numbers into null.
export function canonicalJson(value) {
  const ancestors = new Set();
  function serialize(item) {
    if (item === null || typeof item === 'string' || typeof item === 'boolean' ||
      (typeof item === 'number' && Number.isFinite(item))) return JSON.stringify(item);
    if (typeof item !== 'object' || ancestors.has(item)) throw new TypeError('Expected an acyclic JSON value');
    if (!Array.isArray(item) && ![Object.prototype, null].includes(Object.getPrototypeOf(item))) {
      throw new TypeError('Expected a plain JSON object');
    }
    ancestors.add(item);
    const result = Array.isArray(item)
      ? `[${Array.from(item, serialize).join(',')}]`
      : `{${Object.keys(item).sort().map((key) => `${JSON.stringify(key)}:${serialize(item[key])}`).join(',')}}`;
    ancestors.delete(item);
    return result;
  }
  return serialize(value);
}

export function eventSchemas() {
  return Object.fromEntries(EVENT_TYPES.map((type) => [type, z.toJSONSchema(schemas[type], { io: 'input' })]));
}
