import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createReliefWeatherProvider, weatherCommandSchema } from '../src/relief-weather.js';
import { validateEvent } from '../src/contracts.js';

const NOW = Date.parse('2026-10-15T12:20:00Z');
const UUID = 'c3af3cc6-fbee-46da-90d2-95cb9aad6dc9';
function payload() {
  return { utc_offset_seconds: 0, timezone: 'GMT',
    current_units: { time: 'iso8601', temperature_2m: '\u00b0C', wind_speed_10m: 'm/s', weather_code: 'wmo code' },
    current: { time: '2026-10-15T12:15', temperature_2m: 28.5, wind_speed_10m: 4.2, weather_code: 63 },
    hourly_units: { time: 'iso8601', visibility: 'm' },
    hourly: { time: ['2026-10-15T11:00', '2026-10-15T12:00', '2026-10-15T13:00'], visibility: [9000, 8000, 7000] } };
}
function provider(fetchImpl, options = {}) {
  return createReliefWeatherProvider({ fetchImpl, now: () => NOW, ...options });
}
function response(value = payload(), options) { return new Response(JSON.stringify(value), options); }
async function rejectsPayload(value, code = 'WEATHER_INVALID_RESPONSE') {
  const weather = provider(async () => response(value));
  await assert.rejects(weather.fetch('delhi'), { code });
  await weather.close();
}

test('weather command is strict and bounded to civilian presets and simulation identifiers', () => {
  const command = { commandId: UUID, runId: UUID, expectedRevision: 18, airportId: 'SIM-HUB', location: 'delhi' };
  assert.deepEqual(weatherCommandSchema.parse(command), command);
  for (const change of [{ url: 'https://evil.test' }, { commandId: 'bad' }, { runId: 'bad' },
    { expectedRevision: 19 }, { expectedRevision: -1 }, { expectedRevision: 1.5 }, { airportId: 'real-airport' },
    { airportId: `SIM-${'X'.repeat(17)}` }, { location: 'https://evil.test' }, { location: '__proto__' }]) {
    assert.equal(weatherCommandSchema.safeParse({ ...command, ...change }).success, false);
  }
});

test('fixed HTTPS requests return canonical weather with both sample times and preset provenance', async () => {
  const requests = [];
  const weather = provider(async (url, options) => { requests.push({ url: new URL(url), options }); return response(); });
  for (const location of ['delhi', 'mumbai', 'chennai']) {
    const observation = await weather.fetch(location);
    assert.deepEqual(observation.data, { temperatureC: 28.5, windSpeedMps: 4.2, visibilityM: 8000, condition: 'rain' });
    assert.equal(observation.observedAt, '2026-10-15T12:15:00.000Z');
    assert.equal(observation.validUntil, '2026-10-15T12:35:00.000Z');
    assert.equal(observation.provenance.provider, 'open-meteo');
    assert.equal(observation.provenance.location, location);
    assert.equal(observation.provenance.fetchedAt, '2026-10-15T12:20:00.000Z');
    assert.equal(observation.provenance.weatherTime, observation.observedAt);
    assert.equal(observation.provenance.visibilityTime, '2026-10-15T12:00:00.000Z');
    validateEvent({ schemaVersion: 1, eventId: UUID, sourceId: 'weather-feed', entityId: 'SIM-HUB',
      sequence: 1, type: 'weather.observation', data: observation.data,
      observedAt: observation.observedAt, validUntil: observation.validUntil }, { now: NOW });
  }
  for (const { url, options } of requests) {
    assert.equal(url.origin, 'https://api.open-meteo.com'); assert.equal(url.pathname, '/v1/forecast');
    assert.equal(url.searchParams.get('current'), 'temperature_2m,wind_speed_10m,weather_code');
    assert.equal(url.searchParams.get('hourly'), 'visibility');
    assert.equal(url.searchParams.get('timezone'), 'GMT'); assert.equal(url.searchParams.get('wind_speed_unit'), 'ms');
    assert.equal(options.redirect, 'error'); assert.equal(options.method, 'GET');
  }
  assert.deepEqual(requests.map(r => [Number(r.url.searchParams.get('latitude')), Number(r.url.searchParams.get('longitude'))]),
    [[28.6139, 77.2090], [19.0760, 72.8777], [13.0827, 80.2707]]);
  await weather.close();
});

test('unknown locations and invalid provider limits never initiate a request', async () => {
  const weather = provider(() => { throw new Error('must not fetch'); });
  for (const location of ['__proto__', 'Delhi', '', 'http://localhost', { city: 'delhi' }]) {
    await assert.rejects(weather.fetch(location), { code: 'WEATHER_INVALID_LOCATION' });
  }
  for (const options of [{ timeoutMs: 0 }, { timeoutMs: 60001 }, { timeoutMs: '20' },
    { maxResponseBytes: 0 }, { maxResponseBytes: 131073 }, { fetchImpl: null }, { now: 1 }]) {
    assert.throws(() => createReliefWeatherProvider(options), /configuration/);
  }
  await weather.close();
});

test('nearest visibility selects earlier on ties and permits an explicitly identified future forecast hour', async () => {
  for (const [time, expected] of [['2026-10-15T12:30', '2026-10-15T12:00:00.000Z'],
    ['2026-10-15T12:45', '2026-10-15T13:00:00.000Z']]) {
    const value = payload(); value.current.time = time;
    const weather = provider(async () => response(value), { now: () => Date.parse(`${time}Z`) });
    assert.equal((await weather.fetch('delhi')).provenance.visibilityTime, expected);
    await weather.close();
  }
  const missing = payload(); missing.hourly.visibility[1] = null;
  await rejectsPayload(missing);
});

test('missing fields, malformed timestamps, timezone and units are rejected without invented values', async () => {
  for (const mutate of [v => { delete v.current; }, v => { delete v.current.temperature_2m; },
    v => { v.current.wind_speed_10m = null; }, v => { v.current.temperature_2m = '28'; },
    v => { v.current.weather_code = 100; }, v => { v.current.weather_code = 63.5; },
    v => { v.current.temperature_2m = 61; }, v => { v.current.wind_speed_10m = -1; },
    v => { v.hourly.visibility[1] = 100001; }, v => { v.hourly.time = []; },
    v => { v.hourly.time.pop(); }, v => { v.hourly.time[1] = '2026-02-30T12:00'; },
    v => { v.current.time = '2026-10-15T12:15+05:30'; }, v => { v.utc_offset_seconds = 19800; },
    v => { v.timezone = 'Asia/Kolkata'; }, v => { delete v.utc_offset_seconds; },
    v => { v.current_units.wind_speed_10m = 'km/h'; }, v => { v.hourly_units.visibility = 'km'; },
    v => { v.hourly.time[1] = v.hourly.time[0]; }, v => { v.hourly.time.reverse(); },
    v => { v.hourly.time[1] = '2026-10-15T12:15'; }]) {
    const value = payload(); mutate(value); await rejectsPayload(value);
  }
});

test('stale current data, far-away visibility and future current observations fail freshness', async () => {
  for (const mutate of [v => { v.current.time = '2026-10-15T11:50'; },
    v => { v.current.time = '2026-10-15T12:22'; },
    v => { v.hourly.time = ['2026-10-15T10:00']; v.hourly.visibility = [8000]; }]) {
    const value = payload(); mutate(value); await rejectsPayload(value);
  }
  const weather = provider(async () => response(), { now: () => NOW + 24 * 60 * 60 * 1000 });
  await assert.rejects(weather.fetch('delhi'), { code: 'WEATHER_INVALID_RESPONSE' }); await weather.close();
});

test('only documented WMO categories map to the bounded weather contract', async () => {
  for (const [codes, condition] of [[[0, 1, 2, 3], 'clear'], [[45, 48], 'fog'],
    [[51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82], 'rain'],
    [[71, 73, 75, 77, 85, 86], 'snow'], [[95, 96, 99], 'storm']]) {
    for (const code of codes) {
      const value = payload(); value.current.weather_code = code;
      const weather = provider(async () => response(value));
      assert.equal((await weather.fetch('delhi')).data.condition, condition); await weather.close();
    }
  }
});

test('transport failures and redirect/non-JSON responses expose fixed errors without upstream bodies', async () => {
  for (const fetchImpl of [async () => { throw new Error('secret upstream body'); },
    async () => new Response('secret upstream body', { status: 503 }),
    async () => new Response('secret upstream body', { status: 302, headers: { location: 'http://localhost' } })]) {
    const weather = provider(fetchImpl);
    await assert.rejects(weather.fetch('delhi'), error => error.code === 'WEATHER_UNAVAILABLE' && !error.message.includes('secret'));
    await weather.close();
  }
  const weather = provider(async () => new Response('{broken'));
  await assert.rejects(weather.fetch('delhi'), { code: 'WEATHER_INVALID_RESPONSE' }); await weather.close();
});

test('response size is bounded by both advertised and streamed bytes and rejected bodies are cancelled', async () => {
  for (const headers of [{ 'content-length': '2048' }, {}]) {
    let cancelled = false;
    const weather = provider(async () => new Response(new ReadableStream({
      start(stream) { stream.enqueue(new Uint8Array(1025)); }, cancel() { cancelled = true; }
    }), { headers }), { maxResponseBytes: 1024 });
    await assert.rejects(weather.fetch('delhi'), { code: 'WEATHER_RESPONSE_TOO_LARGE' });
    assert.equal(cancelled, true); await weather.close();
  }
});

test('timeouts cover fetch and stalled body reads, and abort their transports', async () => {
  for (const stalledBody of [false, true]) {
    let signal; let cancelled = false;
    const weather = provider(async (_url, options) => {
      signal = options.signal;
      return stalledBody ? new Response(new ReadableStream({ cancel() { cancelled = true; } })) : new Promise(() => {});
    }, { timeoutMs: 20 });
    await assert.rejects(weather.fetch('delhi'), { code: 'WEATHER_TIMEOUT' });
    assert.equal(signal.aborted, true); if (stalledBody) assert.equal(cancelled, true);
    await weather.close();
  }
});

test('single flight is bounded; close aborts, drains and rejects new requests', async () => {
  let signal;
  const weather = provider(async (_url, options) => { signal = options.signal; return new Promise(() => {}); });
  const pending = weather.fetch('delhi');
  const failed = assert.rejects(pending, { code: 'WEATHER_CLOSED' });
  await assert.rejects(weather.fetch('mumbai'), { code: 'WEATHER_BUSY' });
  await weather.close(); await failed;
  assert.equal(signal.aborted, true);
  await assert.rejects(weather.fetch('delhi'), { code: 'WEATHER_CLOSED' }); await weather.close();
});

test('a transport resolving after shutdown has its body cancelled and cannot return late weather', async () => {
  let resolveFetch; let started; let cancelled = false;
  const entered = new Promise(resolve => { started = resolve; });
  const weather = provider(() => new Promise(resolve => { resolveFetch = resolve; started(); }));
  const pending = weather.fetch('delhi'); const failed = assert.rejects(pending, { code: 'WEATHER_CLOSED' });
  await entered;
  await weather.close(); await failed;
  resolveFetch(new Response(new ReadableStream({ cancel() { cancelled = true; } })));
  await new Promise(resolve => setImmediate(resolve)); assert.equal(cancelled, true);
});

test('close cancels a pending body read and drains the public operation', async () => {
  let reading; let cancelled = false;
  const entered = new Promise(resolve => { reading = resolve; });
  const weather = provider(async () => new Response(new ReadableStream({
    pull() { reading(); }, cancel() { cancelled = true; }
  })));
  const pending = weather.fetch('delhi'); const failed = assert.rejects(pending, { code: 'WEATHER_CLOSED' });
  await entered; await weather.close(); await failed;
  assert.equal(cancelled, true);
});
