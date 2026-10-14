import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { EVENT_TYPES } from './contracts.js';

export function tokenHash(token) { return createHash('sha256').update(token).digest(); }
const moduleRoot = fileURLToPath(new URL('../', import.meta.url));
const identifier = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const tokenPattern = /^[A-Za-z0-9_-]{32,128}$/;
function fail(field) { throw new Error(`Invalid configuration: ${field}.`); }
function integer(env, name, fallback, min, max) {
  const raw = env[name];
  if (raw === undefined || raw === '') return fallback;
  if (!/^\d+$/.test(raw)) fail(name);
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < min || value > max) fail(name);
  return value;
}
function boolean(env, name, fallback = false) {
  if (!env[name]) return fallback;
  if (!['true', 'false'].includes(env[name])) fail(name);
  return env[name] === 'true';
}

/** Validate configuration once; bearer secrets become digests. Treat optional SASL config as secret. */
export function loadConfig(env = process.env) {
  const adminToken = env.INGESTION_ADMIN_TOKEN;
  if (!tokenPattern.test(adminToken ?? '')) fail('INGESTION_ADMIN_TOKEN');
  let sources;
  try { sources = JSON.parse(env.INGESTION_SOURCES_JSON ?? ''); }
  catch { fail('INGESTION_SOURCES_JSON'); }
  if (!Array.isArray(sources) || sources.length < 1 || sources.length > 100) fail('INGESTION_SOURCES_JSON');
  const ids = new Set(); const tokens = new Set([adminToken]);
  sources = sources.map((source) => {
    if (!source || typeof source !== 'object' || Array.isArray(source) ||
      Object.keys(source).some((key) => !['sourceId', 'token', 'types'].includes(key)) ||
      !identifier.test(source.sourceId ?? '') || ids.has(source.sourceId) ||
      !tokenPattern.test(source.token ?? '') || tokens.has(source.token) ||
      !Array.isArray(source.types) || source.types.length < 1 || source.types.length > EVENT_TYPES.length ||
      new Set(source.types).size !== source.types.length || source.types.some((type) => !EVENT_TYPES.includes(type))) fail('INGESTION_SOURCES_JSON');
    ids.add(source.sourceId); tokens.add(source.token);
    return Object.freeze({ sourceId: source.sourceId, digest: tokenHash(source.token), types: Object.freeze([...source.types]) });
  });
  const viewerToken = env.MONITOR_VIEWER_TOKEN;
  if (viewerToken !== undefined && (!tokenPattern.test(viewerToken) || tokens.has(viewerToken))) fail('MONITOR_VIEWER_TOKEN');
  let monitorOrigin;
  if (env.MONITOR_ORIGIN) {
    try {
      const url = new URL(env.MONITOR_ORIGIN);
      if (url.origin !== env.MONITOR_ORIGIN || url.username || url.password ||
        (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)))) fail('MONITOR_ORIGIN');
      monitorOrigin = url.origin;
    } catch { fail('MONITOR_ORIGIN'); }
  }
  const brokers = (env.KAFKA_BROKERS ?? '').split(',').map((s) => s.trim()).filter(Boolean);
  if (brokers.length > 10 || brokers.some((value) => !/^(?:[A-Za-z0-9.-]+|\[[0-9a-fA-F:]+\]):\d{1,5}$/.test(value) ||
    Number(value.slice(value.lastIndexOf(':') + 1)) < 1 || Number(value.slice(value.lastIndexOf(':') + 1)) > 65535)) fail('KAFKA_BROKERS');
  const ssl = boolean(env, 'KAFKA_TLS');
  if (!ssl && brokers.some((value) => !/^(?:localhost|127\.0\.0\.1|\[::1\]):/.test(value))) fail('KAFKA_TLS (required for remote brokers)');
  let sasl;
  if (env.KAFKA_SASL_USERNAME || env.KAFKA_SASL_PASSWORD) {
    const mechanism = env.KAFKA_SASL_MECHANISM ?? 'scram-sha-256';
    if (!env.KAFKA_SASL_USERNAME || !env.KAFKA_SASL_PASSWORD || !['plain', 'scram-sha-256', 'scram-sha-512'].includes(mechanism)) fail('KAFKA_SASL credentials');
    if (!ssl) fail('KAFKA_TLS (required for SASL)');
    sasl = { mechanism, username: env.KAFKA_SASL_USERNAME, password: env.KAFKA_SASL_PASSWORD };
  }
  const host = env.HOST ?? '127.0.0.1';
  if (!/^(?:[A-Za-z0-9.-]+|::1|::)$/.test(host)) fail('HOST');
  return Object.freeze({ host, port: integer(env, 'PORT', 3100, 1, 65535),
    dbPath: env.INGESTION_DB_PATH === ':memory:' ? ':memory:' : resolve(moduleRoot, env.INGESTION_DB_PATH ?? 'var/events.sqlite'),
    adminDigest: tokenHash(adminToken), sources: Object.freeze(sources),
    monitor: Object.freeze({ digest: viewerToken ? tokenHash(viewerToken) : null, origin: monitorOrigin }),
    maxPending: integer(env, 'INGESTION_MAX_PENDING', 10000, 1, 1000000),
    sourceRate: integer(env, 'INGESTION_SOURCE_RATE', 1000, 1, 100000),
    publicRate: integer(env, 'INGESTION_PUBLIC_RATE', 300, 1, 100000),
    adminRate: integer(env, 'INGESTION_ADMIN_RATE', 300, 1, 100000),
    rateWindowMs: integer(env, 'INGESTION_RATE_WINDOW_MS', 60000, 100, 3600000),
    retentionDays: integer(env, 'INGESTION_RETENTION_DAYS', 30, 1, 3650),
    flushIntervalMs: integer(env, 'OUTBOX_INTERVAL_MS', 1000, 100, 60000),
    maxAttempts: integer(env, 'OUTBOX_MAX_ATTEMPTS', 8, 1, 100),
    baseDelayMs: integer(env, 'OUTBOX_BASE_DELAY_MS', 1000, 10, 60000),
    maxDelayMs: integer(env, 'OUTBOX_MAX_DELAY_MS', 60000, 10, 3600000),
    kafka: Object.freeze({ brokers: Object.freeze(brokers), ssl, sasl,
      requestTimeout: integer(env, 'KAFKA_REQUEST_TIMEOUT_MS', 3000, 100, 30000) }),
  });
}
