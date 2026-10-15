import express from 'express';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import { canonicalJson, EVENT_TYPES } from '../contracts/events.js';
import { tokenHash } from '../platform/config.js';
import { ApiError } from '../platform/errors.js';

/** Data quality indicators only; no inferred readiness, assignment or recommendations. */
export function monitoringSnapshot(store, filters = {}, now = Date.now()) {
  const selected = store.monitoringState(filters);
  const records = selected.records.map((record) => {
    const event = record.event; const freshness = Date.parse(event.validUntil) > now ? 'current' : 'expired';
    const flags = [];
    if (freshness === 'expired') flags.push('expired');
    if (record.warnings.includes('sequence_gap')) flags.push('sequence_gap');
    if (event.type === 'aircraft.status' && event.data.maintenanceDueAt && Date.parse(event.data.maintenanceDueAt) <= now) flags.push('maintenance_date_passed');
    return { ...record, freshness, ageMs: Math.max(0, now - Date.parse(event.observedAt)), flags,
      reportedStatus: event.data.status ?? event.data.condition ?? event.data.category ?? null };
  });
  const groups = new Map();
  for (const record of records) {
    if (record.freshness !== 'current') continue;
    const key = `${record.event.type}:${record.event.entityId}`;
    const group = groups.get(key) ?? []; group.push(record); groups.set(key, group);
  }
  for (const group of groups.values()) {
    if (new Set(group.map((r) => canonicalJson(r.event.data))).size > 1) {
      for (const record of group) record.flags.push('source_disagreement');
    }
  }
  const summary = { total: records.length, current: 0, expired: 0, sequenceGaps: 0, disagreements: 0, byType: {} };
  for (const type of EVENT_TYPES) summary.byType[type] = 0;
  for (const record of records) {
    summary[record.freshness]++; summary.byType[record.event.type]++;
    if (record.flags.includes('sequence_gap')) summary.sequenceGaps++;
    if (record.flags.includes('source_disagreement')) summary.disagreements++;
  }
  return { generatedAt: new Date(now).toISOString(), scope: { limit: 1000, shown: records.length, truncated: selected.truncated },
    summary, records, delivery: store.metrics().outbox, deliveryScope: 'global_outbox' };
}

const SESSION_MS = 30 * 60 * 1000;
const COOKIE = 'logistics_viewer';
const TOKEN = /^[A-Za-z0-9_-]{32,128}$/;
const identifier = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/);
const query = z.strictObject({ type: z.enum(EVENT_TYPES).optional(), sourceId: identifier.optional() });
function parse(schema, input) {
  const result = schema.safeParse(input);
  if (!result.success) throw new ApiError(422, 'INVALID_QUERY', 'Request does not match the expected contract.');
  return result.data;
}
function cookieValue(req) {
  const values = (req.headers.cookie ?? '').split(';').map((s) => s.trim()).filter((s) => s.startsWith(`${COOKIE}=`));
  if (values.length !== 1) return null;
  const value = values[0].slice(COOKIE.length + 1);
  return TOKEN.test(value) ? tokenHash(value).toString('hex') : null;
}

export function mountMonitoring(app, { config, store, simulation, now = Date.now }) {
  const sessions = new Map(); const settings = config.monitor ?? { digest: null };
  const router = express.Router();
  router.use((_req, res, next) => { res.setHeader('Cache-Control', 'no-store'); next(); });
  function enabled() {
    if (!settings.digest) throw new ApiError(503, 'VIEWER_DISABLED', 'Read-only viewer access is not configured.');
  }
  function cleanSessions() { for (const [key, expiry] of sessions) if (expiry <= now()) sessions.delete(key); }
  function sameOrigin(req, _res, next) {
    enabled();
    let allowed = false;
    try {
      const origin = new URL(req.headers.origin);
      if (settings.origin) allowed = req.headers.origin === settings.origin;
      else allowed = origin.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(origin.hostname) &&
        origin.host === req.headers.host && Number(origin.port || 80) === req.socket.localPort;
    } catch { /* Missing or opaque origins are rejected. */ }
    if (!allowed) throw new ApiError(403, 'ORIGIN_FORBIDDEN', 'A configured same-origin request is required.');
    next();
  }
  const json = [(req, _res, next) => {
    if (!req.is('application/json')) throw new ApiError(415, 'UNSUPPORTED_MEDIA_TYPE', 'Use application/json.'); next();
  }, express.json({ limit: '4kb', strict: true, inflate: false })];
  const cookieOptions = { httpOnly: true, sameSite: 'strict', secure: settings.origin?.startsWith('https:') ?? false,
    path: '/monitor' };
  router.post('/session', sameOrigin, ...json, (req, res) => {
    const input = parse(z.strictObject({ token: z.string().max(128) }), req.body);
    if (!TOKEN.test(input.token) || !timingSafeEqual(tokenHash(input.token), settings.digest)) throw new ApiError(401, 'UNAUTHORIZED', 'Valid viewer credentials are required.');
    cleanSessions();
    const old = cookieValue(req);
    if (old) sessions.delete(old);
    if (sessions.size >= 200) throw new ApiError(503, 'SESSION_CAPACITY', 'Viewer session capacity reached.');
    const token = randomBytes(36).toString('base64url'); sessions.set(tokenHash(token).toString('hex'), now() + SESSION_MS);
    res.cookie(COOKIE, token, { ...cookieOptions, maxAge: SESSION_MS }); res.json({ status: 'authenticated', expiresAt: new Date(now() + SESSION_MS).toISOString() });
  });
  router.post('/logout', sameOrigin, ...json, (req, res) => {
    parse(z.strictObject({}), req.body); const key = cookieValue(req); if (key) sessions.delete(key);
    res.clearCookie(COOKIE, cookieOptions); res.json({ status: 'signed_out' });
  });
  router.get('/api/snapshot', (req, res) => {
    enabled(); cleanSessions(); const key = cookieValue(req);
    if (!key || !sessions.has(key)) throw new ApiError(401, 'UNAUTHORIZED', 'Sign in with read-only viewer credentials.');
    res.json(monitoringSnapshot(store, parse(query, req.query), now()));
  });
  router.get('/api/simulation', (req, res) => {
    enabled(); cleanSessions(); const key = cookieValue(req);
    if (!key || !sessions.has(key)) throw new ApiError(401, 'UNAUTHORIZED', 'Sign in with read-only viewer credentials.');
    parse(z.strictObject({}), req.query);
    res.json(simulation?.snapshot() ?? { status: 'idle' });
  });
  router.use(express.static(fileURLToPath(new URL('../../dashboard/', import.meta.url)), { index: 'index.html', dotfiles: 'deny', fallthrough: true }));
  app.use('/monitor', router);
}
