import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadConfig } from '../src/platform/config.js';
import { fileURLToPath } from 'node:url';

export function environment(overrides = {}) {
  return { INGESTION_ADMIN_TOKEN: 'test-admin-'.padEnd(48, 'A'),
    INGESTION_SOURCES_JSON: JSON.stringify([{ sourceId: 'test-source', token: 'test-source-'.padEnd(48, 'B'), types: ['aircraft.status'] }]),
    INGESTION_DB_PATH: ':memory:', ...overrides };
}
test('configuration is fail-closed without source and admin credentials', () => {
  assert.throws(() => loadConfig({}), /configuration/i);
  assert.throws(() => loadConfig(environment({ INGESTION_ADMIN_TOKEN: 'short' })), /configuration/i);
});
test('safe defaults bind to localhost and disable broker delivery', () => {
  const config = loadConfig(environment());
  assert.equal(config.host, '127.0.0.1'); assert.equal(config.port, 3100);
  assert.equal(config.kafka.brokers.length, 0); assert.equal(config.maxPending, 10000);
  assert.equal(config.sources[0].sourceId, 'test-source');
  assert.ok(!JSON.stringify(config).includes('test-source-B'));
});

test('relocated configuration preserves the service database root', () => {
  const config = loadConfig(environment({ INGESTION_DB_PATH: 'var/events.sqlite' }));
  assert.equal(config.dbPath, fileURLToPath(new URL('../var/events.sqlite', import.meta.url)));
});
test('invalid limits, boolean switches, duplicate credentials, and unknown types fail at startup', () => {
  for (const overrides of [{ PORT: 'not-a-port' }, { PORT: '0' }, { INGESTION_MAX_PENDING: '-1' }, { KAFKA_TLS: 'maybe' },
    { INGESTION_SOURCES_JSON: '[]' }, { INGESTION_SOURCES_JSON: '{broken-json' },
    { INGESTION_SOURCES_JSON: JSON.stringify([{ sourceId: 'test-source', token: 's'.repeat(40), types: ['weapons.assignment'] }]) },
    { INGESTION_SOURCES_JSON: JSON.stringify([{ sourceId: 'test-source', token: 'test-admin-'.padEnd(48, 'A'), types: ['aircraft.status'] }]) }]) {
    assert.throws(() => loadConfig(environment(overrides)), /configuration/i);
  }
});
test('remote Kafka requires TLS and complete optional SASL credentials', () => {
  assert.throws(() => loadConfig(environment({ KAFKA_BROKERS: 'broker.example:9092' })), /configuration/i);
  const config = loadConfig(environment({ KAFKA_BROKERS: 'broker.example:9093', KAFKA_TLS: 'true' }));
  assert.equal(config.kafka.ssl, true);
  assert.throws(() => loadConfig(environment({ KAFKA_BROKERS: 'localhost:29092', KAFKA_SASL_USERNAME: 'user' })), /configuration/i);
});
