import kafkajs from 'kafkajs';
import { canonicalJson } from './contracts.js';

const { Kafka, logLevel } = kafkajs;

/** send() resolves only after a real broker acknowledgement. */
export function createKafkaAdapter(config) {
  const kafka = new Kafka({ clientId: 'logistics-ingestion', brokers: config.brokers,
    ssl: config.ssl, sasl: config.sasl, requestTimeout: config.requestTimeout,
    connectionTimeout: config.requestTimeout, retry: { retries: 0 }, logLevel: logLevel.NOTHING });
  const producer = kafka.producer({ allowAutoTopicCreation: false, maxInFlightRequests: 1 });
  let connected = false;
  return {
    async send({ topic, key, event }) {
      try {
        if (!connected) { await producer.connect(); connected = true; }
        const metadata = await producer.send({ topic, acks: -1, timeout: config.requestTimeout,
          messages: [{ key, value: canonicalJson(event), headers: {
            'event-id': event.eventId, 'schema-version': String(event.schemaVersion), 'source-sequence': String(event.sequence),
          } }] });
        if (!Array.isArray(metadata) || metadata.length === 0) throw new Error('Missing delivery acknowledgement.');
      } catch (error) {
        connected = false;
        // Disconnect cleanup is best-effort; the original delivery failure is propagated to the durable outbox.
        try { await producer.disconnect(); } catch { /* do not mask delivery failure */ }
        throw error;
      }
    },
    async close() { connected = false; await producer.disconnect(); },
  };
}

export class OutboxPublisher {
  constructor({ store, adapter = null, now = Date.now, logger = () => {}, batchSize = 20,
    maxAttempts = 8, baseDelayMs = 1000, maxDelayMs = 60000, drainBudgetMs = 5000 }) {
    this.store = store; this.adapter = adapter; this.now = now; this.logger = logger;
    this.batchSize = batchSize; this.retry = { maxAttempts, baseDelayMs, maxDelayMs, code: 'PUBLISH_FAILED' };
    this.drainBudgetMs = drainBudgetMs; this.enabled = Boolean(adapter);
    this.active = null; this.timer = null; this.stopped = false; this.stopPromise = null;
    this.lastSuccessAt = null; this.lastFailureAt = null;
  }

  diagnostics() {
    return { enabled: this.enabled, stopped: this.stopped, active: Boolean(this.active),
      lastSuccessAt: this.lastSuccessAt, lastFailureAt: this.lastFailureAt };
  }

  flush() {
    if (this.active) return this.active;
    if (!this.enabled || this.stopped) return Promise.resolve({ enabled: this.enabled, attempted: 0, published: 0, failed: 0 });
    this.active = this.drain().finally(() => { this.active = null; });
    return this.active;
  }

  async drain() {
    const result = { enabled: true, attempted: 0, published: 0, failed: 0 };
    const start = performance.now();
    for (const record of this.store.pending({ limit: this.batchSize })) {
      if (this.stopped || performance.now() - start >= this.drainBudgetMs) break;
      result.attempted++;
      try {
        await this.adapter.send(record);
      } catch {
        this.store.markFailed(record.cursor, this.retry);
        this.lastFailureAt = new Date(this.now()).toISOString(); result.failed++;
        this.logger('outbox.publish_failed', { eventId: record.eventId, code: 'PUBLISH_FAILED' });
        break; // A broker outage should not penalize the entire selected backlog in one drain.
      }
      // A store failure after Kafka ACK deliberately propagates: the record remains queued and may be delivered again.
      this.store.markPublished(record.cursor);
      this.lastSuccessAt = new Date(this.now()).toISOString(); result.published++;
    }
    return result;
  }

  start(intervalMs = 1000) {
    if (!this.enabled || this.stopped || this.timer) return;
    const poll = () => this.flush().catch(() => this.logger('outbox.store_failed', { code: 'STORE_FAILURE' }));
    this.timer = setInterval(poll, intervalMs); this.timer.unref(); poll();
  }

  stop() {
    if (this.stopPromise) return this.stopPromise;
    this.stopped = true; clearInterval(this.timer); this.timer = null;
    this.stopPromise = (async () => {
      try { if (this.active) await this.active; }
      finally { await this.adapter?.close?.(); }
    })();
    return this.stopPromise;
  }
}
