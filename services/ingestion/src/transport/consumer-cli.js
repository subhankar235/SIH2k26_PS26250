import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadConfig } from '../platform/config.js';
import { ConsumerStore } from './consumer-store.js';
import { createKafkaConsumer, KafkaReadModelWorker } from './consumer.js';

const moduleRoot = fileURLToPath(new URL('../../', import.meta.url));
const invalid = (name) => { throw new Error(`Invalid consumer configuration: ${name}.`); };
function integer(env, name, fallback, min, max) {
  const raw = env[name]; if (raw === undefined || raw === '') return fallback;
  if (!/^\d+$/.test(raw)) invalid(name);
  const value = Number(raw); if (!Number.isSafeInteger(value) || value < min || value > max) invalid(name); return value;
}
export function loadConsumerConfig(env = process.env) {
  const groupId = env.CONSUMER_GROUP_ID ?? 'logistics-read-model-v1';
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(groupId)) invalid('CONSUMER_GROUP_ID');
  const path = resolve(moduleRoot, env.CONSUMER_DB_PATH ?? 'var/read-model.sqlite');
  const ingestion = resolve(moduleRoot, env.INGESTION_DB_PATH ?? 'var/events.sqlite');
  if (path.toLowerCase() === ingestion.toLowerCase()) invalid('CONSUMER_DB_PATH');
  return { path, groupId,
    maxEvents: integer(env, 'CONSUMER_MAX_EVENTS', 100000, 1, 1000000),
    maxQuarantine: integer(env, 'CONSUMER_MAX_QUARANTINE', 1000, 1, 100000),
    maxCheckpoints: integer(env, 'CONSUMER_MAX_CHECKPOINTS', 10000, 1, 100000),
    maxMessageBytes: integer(env, 'CONSUMER_MAX_MESSAGE_BYTES', 65536, 1024, 1048576),
    maxDatabaseBytes: integer(env, 'CONSUMER_MAX_DB_BYTES', 268435456, 1048576, 2147483648),
  };
}

export async function runConsumer(env = process.env) {
  const appConfig = loadConfig(env); const config = loadConsumerConfig(env);
  if (!appConfig.kafka.brokers.length) invalid('KAFKA_BROKERS');
  const store = new ConsumerStore(config); let worker; let stopping;
  const shutdown = () => {
    if (stopping) return stopping;
    stopping = (async () => {
      const deadline = setTimeout(() => { console.error('consumer.shutdown_timeout'); process.exit(1); }, 15000);
      deadline.unref();
      try { await worker.stop(); } finally { clearTimeout(deadline); store.close(); }
    })(); return stopping;
  };
  const fail = () => {
    process.exitCode = 1; console.error('consumer.failed');
    void shutdown().catch(() => { console.error('consumer.shutdown_failed'); });
  };
  worker = new KafkaReadModelWorker({ store, consumer: createKafkaConsumer(appConfig.kafka, config.groupId), onFailure: fail });
  try { await worker.start(); } catch { await shutdown(); throw new Error('consumer.start_failed'); }
  const signal = () => { void shutdown().catch(fail); };
  process.once('SIGINT', signal); process.once('SIGTERM', signal);
  console.log('consumer.started');
  return { store, worker, stop: async () => { process.removeListener('SIGINT', signal); process.removeListener('SIGTERM', signal); await shutdown(); } };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runConsumer().catch(() => { process.exitCode = 1; console.error('consumer.start_failed'); });
}
