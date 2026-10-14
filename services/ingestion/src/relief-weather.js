import { z } from 'zod';
import { ApiError } from './errors.js';

export const weatherCommandSchema = z.strictObject({
  commandId: z.uuid(), runId: z.uuid(), expectedRevision: z.number().int().min(0).max(18),
  airportId: z.string().regex(/^SIM-[A-Za-z0-9_-]{1,16}$/),
  location: z.enum(['delhi', 'mumbai', 'chennai']),
});

const LOCATIONS = new Map([
  ['delhi', Object.freeze({ latitude: 28.6139, longitude: 77.2090 })],
  ['mumbai', Object.freeze({ latitude: 19.0760, longitude: 72.8777 })],
  ['chennai', Object.freeze({ latitude: 13.0827, longitude: 80.2707 })],
]);
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const CODES = new Map([
  ...[0, 1, 2, 3].map(code => [code, 'clear']),
  ...[45, 48].map(code => [code, 'fog']),
  ...[51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].map(code => [code, 'rain']),
  ...[71, 73, 75, 77, 85, 86].map(code => [code, 'snow']),
  ...[95, 96, 97, 99].map(code => [code, 'storm']),
]);
const timestamp = z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z?$/)
  .refine(value => z.iso.datetime({ local: true }).safeParse(value).success)
  .transform(value => Date.parse(value.endsWith('Z') ? value : `${value}Z`));
// Provider metadata may grow, but every field used in a canonical observation is validated.
const responseSchema = z.object({
  utc_offset_seconds: z.literal(0), timezone: z.enum(['GMT', 'UTC']),
  current_units: z.object({ time: z.literal('iso8601'), temperature_2m: z.literal('\u00b0C'),
    wind_speed_10m: z.literal('m/s'), weather_code: z.literal('wmo code') }),
  current: z.object({ time: timestamp, temperature_2m: z.number().min(-100).max(60),
    wind_speed_10m: z.number().min(0).max(150), weather_code: z.number().int().refine(code => CODES.has(code)) }),
  hourly_units: z.object({ time: z.literal('iso8601'), visibility: z.literal('m') }),
  hourly: z.object({ time: z.array(timestamp).min(1).max(48),
    visibility: z.array(z.number().min(0).max(100_000).nullable()).min(1).max(48) }),
});

const ERRORS = Object.freeze({
  WEATHER_INVALID_LOCATION: [422, 'Weather location must be a supported civilian preset.'],
  WEATHER_BUSY: [503, 'Weather refresh is already in progress.'],
  WEATHER_CLOSED: [503, 'Weather provider is stopping.'],
  WEATHER_TIMEOUT: [504, 'Weather provider request timed out.'],
  WEATHER_UNAVAILABLE: [502, 'Weather provider is unavailable.'],
  WEATHER_RESPONSE_TOO_LARGE: [502, 'Weather provider response exceeds the size limit.'],
  WEATHER_INVALID_RESPONSE: [502, 'Weather provider returned unusable data.'],
});
class WeatherError extends ApiError {
  constructor(code) { super(ERRORS[code][0], code, ERRORS[code][1]); }
}
function failure(code) { return new WeatherError(code); }
function cancelBody(response) { void response?.body?.cancel().catch(() => {}); }

async function readLimited(response, maximum, signal) {
  if (signal.aborted) { cancelBody(response); throw signal.reason; }
  if (!response?.ok || response.redirected) { cancelBody(response); throw failure('WEATHER_UNAVAILABLE'); }
  const advertised = Number(response.headers.get('content-length'));
  if (Number.isFinite(advertised) && advertised > maximum) {
    cancelBody(response); throw failure('WEATHER_RESPONSE_TOO_LARGE');
  }
  if (!response.body) throw failure('WEATHER_INVALID_RESPONSE');
  const reader = response.body.getReader();
  const cancel = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener('abort', cancel, { once: true });
  const chunks = []; let bytes = 0;
  try {
    while (true) {
      if (signal.aborted) throw signal.reason;
      const { done, value } = await reader.read();
      if (signal.aborted) throw signal.reason;
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maximum) { cancel(); throw failure('WEATHER_RESPONSE_TOO_LARGE'); }
      chunks.push(value);
    }
  } finally {
    signal.removeEventListener('abort', cancel); reader.releaseLock();
  }
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks))); }
  catch { throw failure('WEATHER_INVALID_RESPONSE'); }
}

function observation(payload, location, coordinates, fetchedAt) {
  const parsed = responseSchema.safeParse(payload);
  if (!parsed.success || !Number.isFinite(fetchedAt) || Math.abs(fetchedAt) > 8.64e15) throw failure('WEATHER_INVALID_RESPONSE');
  const { current, hourly } = parsed.data;
  const weatherTime = current.time;
  if (weatherTime > fetchedAt + MINUTE || weatherTime <= fetchedAt - 30 * MINUTE ||
    hourly.time.length !== hourly.visibility.length ||
    hourly.time.some((time, index) => time % HOUR !== 0 || (index > 0 && time <= hourly.time[index - 1]))) {
    throw failure('WEATHER_INVALID_RESPONSE');
  }
  // Ascending hours and a strict comparison make an equal-distance tie choose the earlier hour.
  let nearest = 0;
  for (let index = 1; index < hourly.time.length; index++) {
    if (Math.abs(hourly.time[index] - weatherTime) < Math.abs(hourly.time[nearest] - weatherTime)) nearest = index;
  }
  const visibilityTime = hourly.time[nearest];
  if (Math.abs(visibilityTime - weatherTime) > 30 * MINUTE || hourly.visibility[nearest] === null) {
    throw failure('WEATHER_INVALID_RESPONSE');
  }
  const validUntil = Math.min(weatherTime + 30 * MINUTE, visibilityTime + HOUR, fetchedAt + 15 * MINUTE);
  if (validUntil <= fetchedAt || validUntil <= weatherTime) throw failure('WEATHER_INVALID_RESPONSE');
  return {
    data: { temperatureC: current.temperature_2m, windSpeedMps: current.wind_speed_10m,
      visibilityM: hourly.visibility[nearest], condition: CODES.get(current.weather_code) },
    observedAt: new Date(weatherTime).toISOString(), validUntil: new Date(validUntil).toISOString(),
    provenance: { provider: 'open-meteo', location, ...coordinates, fetchedAt: new Date(fetchedAt).toISOString(),
      weatherTime: new Date(weatherTime).toISOString(), visibilityTime: new Date(visibilityTime).toISOString() },
  };
}

export function createReliefWeatherProvider({ fetchImpl = globalThis.fetch, now = Date.now,
  timeoutMs = 10000, maxResponseBytes = 65536 } = {}) {
  if (typeof fetchImpl !== 'function' || typeof now !== 'function' ||
    !Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 60000 ||
    !Number.isSafeInteger(maxResponseBytes) || maxResponseBytes < 1 || maxResponseBytes > 131072) {
    throw new TypeError('Invalid relief weather provider configuration.');
  }
  let closed = false; let active = null; let controller = null;
  return {
    async fetch(location) {
      if (closed) throw failure('WEATHER_CLOSED');
      if (!LOCATIONS.has(location)) throw failure('WEATHER_INVALID_LOCATION');
      if (active) throw failure('WEATHER_BUSY');
      const coordinates = LOCATIONS.get(location);
      const url = new URL('https://api.open-meteo.com/v1/forecast');
      url.search = new URLSearchParams({ ...coordinates, current: 'temperature_2m,wind_speed_10m,weather_code',
        hourly: 'visibility', temperature_unit: 'celsius', wind_speed_unit: 'ms', timezone: 'GMT',
        timeformat: 'iso8601', forecast_hours: '3', past_hours: '1' }).toString();
      const requestController = new AbortController(); controller = requestController;
      const timer = setTimeout(() => requestController.abort(failure('WEATHER_TIMEOUT')), timeoutMs);
      let abortListener;
      const aborted = new Promise((_resolve, reject) => {
        abortListener = () => reject(requestController.signal.reason);
        requestController.signal.addEventListener('abort', abortListener, { once: true });
      });
      const request = Promise.resolve().then(async () => {
        if (requestController.signal.aborted) throw requestController.signal.reason;
        const response = await fetchImpl(url.href, { method: 'GET', redirect: 'error',
          headers: { Accept: 'application/json' }, signal: requestController.signal });
        const payload = await readLimited(response, maxResponseBytes, requestController.signal);
        if (requestController.signal.aborted) throw requestController.signal.reason;
        return observation(payload, location, coordinates, now());
      });
      const operation = Promise.race([request, aborted]); active = operation;
      try { return await operation; }
      catch (error) { throw error instanceof WeatherError ? error : failure('WEATHER_UNAVAILABLE'); }
      finally {
        clearTimeout(timer); requestController.signal.removeEventListener('abort', abortListener);
        if (active === operation) active = null;
        if (controller === requestController) controller = null;
      }
    },
    async close() {
      closed = true; controller?.abort(failure('WEATHER_CLOSED'));
      if (active) await active.catch(() => {});
    },
  };
}
