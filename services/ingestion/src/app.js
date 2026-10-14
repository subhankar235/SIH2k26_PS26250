import express from 'express';
import helmet from 'helmet';
import { randomUUID, timingSafeEqual } from 'node:crypto';
import { z } from 'zod';
import { ApiError } from './errors.js';
import { EVENT_TYPES, eventSchemas } from './contracts.js';
import { tokenHash } from './config.js';
import { IngestionService } from './ingestion.js';
import { mountMonitoring } from './monitoring.js';

const id = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/);
const cursor = z.string().regex(/^\d+$/).transform(Number).refine(Number.isSafeInteger).refine((n) => n >= 0);
const limit = cursor.refine((n) => n >= 1 && n <= 100);
const historyQuery = z.strictObject({ after: cursor.optional(), limit: limit.optional(),
  sourceId: id.optional(), type: z.enum(EVENT_TYPES).optional(), entityId: id.optional() });
const outboxQuery = z.strictObject({ after: cursor.optional(), limit: limit.optional(), status: z.enum(['queued', 'dead', 'published']).optional() });
function parse(schema, value, code = 'INVALID_QUERY') {
  const result = schema.safeParse(value);
  if (!result.success) throw new ApiError(422, code, 'Request does not match the expected contract.');
  return result.data;
}

/** Bounded single-process limiter; multi-replica deployments need a shared limiter. */
function limiter({ maximum, windowMs, now, maxKeys = 10000 }) {
  const buckets = new Map();
  return (key, weight = 1) => {
    const time = now(); let bucket = buckets.get(key);
    if (!bucket || bucket.until <= time) {
      if (buckets.size >= maxKeys) {
        for (const [name, value] of buckets) if (value.until <= time) buckets.delete(name);
      }
      if (!buckets.has(key) && buckets.size >= maxKeys) throw new ApiError(429, 'RATE_LIMITED', 'Rate limit capacity reached.');
      bucket = { count: 0, until: time + windowMs }; buckets.set(key, bucket);
    }
    if (bucket.count + weight > maximum) {
      const error = new ApiError(429, 'RATE_LIMITED', 'Rate limit exceeded.');
      error.retryAfter = Math.max(1, Math.ceil((bucket.until - time) / 1000)); throw error;
    }
    bucket.count += weight;
  };
}

export function createApp({ config, store, publisher, now = Date.now, logger = () => {}, isReady = () => true }) {
  const app = express(); app.disable('x-powered-by'); app.set('trust proxy', false);
  app.set('query parser', 'simple');
  const ingest = new IngestionService({ store, now });
  const http = { requests: 0, failures: 0 };
  const ipLimit = limiter({ maximum: config.publicRate, windowMs: config.rateWindowMs, now });
  const sourceLimit = limiter({ maximum: config.sourceRate, windowMs: config.rateWindowMs, now, maxKeys: 100 });
  const adminLimit = limiter({ maximum: config.adminRate, windowMs: config.rateWindowMs, now, maxKeys: 1 });
  const schemas = eventSchemas();
  app.use((req, res, next) => {
    req.requestId = randomUUID(); res.setHeader('X-Request-ID', req.requestId);
    const start = performance.now(); http.requests++;
    res.once('finish', () => {
      if (res.statusCode >= 400) http.failures++;
      logger('http.request', { requestId: req.requestId, method: req.method, status: res.statusCode,
        durationMs: Math.round(performance.now() - start) });
    });
    next();
  });
  app.use(helmet());
  app.use((req, _res, next) => { ipLimit(req.ip ?? 'unknown'); next(); });
  app.get('/health/live', (_req, res) => res.json({ status: 'ok' }));
  app.get('/health/ready', (_req, res) => {
    let ready = false; try { ready = isReady() && store.ready(); } catch { /* readiness is fail-closed */ }
    res.status(ready ? 200 : 503).json({ status: ready ? 'ready' : 'unavailable' });
  });

  function authenticate(kind) {
    return (req, _res, next) => {
      const match = /^Bearer ([A-Za-z0-9_-]{32,128})$/.exec(req.headers.authorization ?? '');
      if (!match) throw new ApiError(401, 'UNAUTHORIZED', 'Valid bearer credentials are required.');
      const digest = tokenHash(match[1]);
      if (kind === 'admin') {
        if (!timingSafeEqual(digest, config.adminDigest)) throw new ApiError(401, 'UNAUTHORIZED', 'Valid admin credentials are required.');
        adminLimit('admin');
      } else {
        // Evaluate every configured digest; do not expose a matching position via an early return.
        let source;
        for (const candidate of config.sources) if (timingSafeEqual(digest, candidate.digest)) source = candidate;
        if (!source) throw new ApiError(401, 'UNAUTHORIZED', 'Valid source credentials are required.');
        req.source = source;
      }
      next();
    };
  }
  const json = [
    (req, _res, next) => { if (!req.is('application/json')) throw new ApiError(415, 'UNSUPPORTED_MEDIA_TYPE', 'Use application/json.'); next(); },
    express.json({ limit: '256kb', strict: true, inflate: false }),
  ];
  const router = express.Router();
  router.post('/events', authenticate('source'), ...json, (req, res) => {
    sourceLimit(req.source.sourceId);
    const [receipt] = ingest.accept([req.body], req.source);
    res.status(receipt.duplicate ? 200 : 201).json(receipt);
  });
  router.post('/events/batch', authenticate('source'), ...json, (req, res) => {
    const input = parse(z.strictObject({ events: z.array(z.unknown()).min(1).max(100) }), req.body, 'INVALID_BATCH');
    sourceLimit(req.source.sourceId, input.events.length);
    res.json({ receipts: ingest.accept(input.events, req.source) });
  });
  router.use(authenticate('admin'));
  router.get('/events', (req, res) => res.json(store.listEvents(parse(historyQuery, req.query))));
  router.get('/events/:eventId', (req, res) => {
    const eventId = parse(z.uuid(), req.params.eventId);
    const result = store.getEvent(eventId);
    if (!result) throw new ApiError(404, 'NOT_FOUND', 'Event not found.');
    res.json(result);
  });
  router.get('/state', (req, res) => res.json(store.listState(parse(historyQuery, req.query))));
  router.get('/outbox', (req, res) => res.json(store.listOutbox(parse(outboxQuery, req.query))));
  router.post('/outbox/:eventId/retry', ...json, (req, res) => {
    parse(z.strictObject({}), req.body);
    res.json(store.retryDead(parse(z.uuid(), req.params.eventId)));
  });
  router.post('/outbox/flush', ...json, async (req, res) => {
    parse(z.strictObject({}), req.body);
    if (!publisher.enabled) throw new ApiError(503, 'BROKER_DISABLED', 'Broker delivery is not configured.');
    const result = await publisher.flush();
    if (result.failed > 0) throw new ApiError(503, 'BROKER_UNAVAILABLE', 'Delivery is unavailable; work remains durably queued or dead.', result);
    res.json(result);
  });
  router.post('/retention', ...json, (req, res) => {
    const input = parse(z.strictObject({ limit: z.number().int().min(1).max(1000).optional(),
      after: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER).optional() }), req.body);
    res.json(store.purge({ before: now() - config.retentionDays * 86400000, limit: input.limit ?? 1000, after: input.after ?? 0 }));
  });
  router.get('/metrics', (_req, res) => res.json({ http: { ...http }, store: store.metrics(), broker: publisher.diagnostics?.() ?? { enabled: publisher.enabled } }));
  router.get('/schema', (_req, res) => res.json({ schemaVersion: 1, schemas,
    runtimeRules: ['Cross-field consistency and observation-time checks are enforced by runtime validation.'] }));
  app.use('/v1', router);
  mountMonitoring(app, { config, store, now });
  app.use((_req, _res, next) => next(new ApiError(404, 'NOT_FOUND', 'Endpoint not found.')));
  app.use((error, req, res, _next) => {
    if (res.headersSent) { res.destroy(); return; }
    let status = 500; let code = 'INTERNAL_ERROR'; let message = 'Request could not be completed.'; let details;
    if (error instanceof ApiError) ({ status, code, message, details } = error);
    else if (error.type === 'entity.too.large') { status = 413; code = 'BODY_TOO_LARGE'; message = 'Request body exceeds 256 KiB.'; }
    else if (error.type === 'entity.parse.failed') { status = 400; code = 'INVALID_JSON'; message = 'Request body must contain valid JSON.'; }
    else if (error.type === 'encoding.unsupported' || error.type === 'charset.unsupported') { status = 415; code = 'UNSUPPORTED_MEDIA_TYPE'; message = 'Unsupported body encoding.'; }
    if (error.retryAfter) res.setHeader('Retry-After', error.retryAfter);
    if (status === 503) res.setHeader('Retry-After', 5);
    res.status(status).json({ error: { code, message, ...(details ? { details } : {}) }, requestId: req.requestId });
  });
  return app;
}
