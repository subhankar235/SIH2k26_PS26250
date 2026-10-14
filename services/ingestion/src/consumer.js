import kafkajs from 'kafkajs';
import { TOPICS } from './contracts.js';

const { Kafka, logLevel } = kafkajs;
export function createKafkaConsumer(config, groupId) {
  const kafka = new Kafka({ clientId: 'logistics-read-model', brokers: config.brokers,
    ssl: config.ssl, sasl: config.sasl, requestTimeout: config.requestTimeout,
    connectionTimeout: config.requestTimeout, retry: { retries: 0 }, logLevel: logLevel.NOTHING });
  return kafka.consumer({ groupId, allowAutoTopicCreation: false, maxBytesPerPartition: 1048576,
    maxBytes: 5242880, retry: { retries: 0, restartOnFailure: async () => false } });
}

/** At-least-once broker delivery with durable idempotent projection. Database and broker are not one transaction. */
export class KafkaReadModelWorker {
  constructor({ store, consumer, onFailure = () => {} }) {
    this.store = store; this.consumer = consumer; this.onFailure = onFailure; this.stopped = false;
    if (consumer.on && consumer.events?.CRASH) consumer.on(consumer.events.CRASH, () => this.onFailure('CONSUMER_CRASH'));
  }
  async process(record) {
    const result = this.store.process(record);
    await this.consumer.commitOffsets([{ topic: record.topic, partition: record.partition, offset: result.nextOffset }]);
    return result;
  }
  async start() {
    await this.consumer.connect();
    await this.consumer.subscribe({ topics: Object.values(TOPICS), fromBeginning: true });
    await this.consumer.run({ autoCommit: false, eachBatchAutoResolve: false, partitionsConsumedConcurrently: 1,
      eachBatch: async ({ batch, resolveOffset, heartbeat, isRunning, isStale }) => {
        for (const message of batch.messages) {
          if (this.stopped || !isRunning() || isStale()) break;
          await this.process({ topic: batch.topic, partition: batch.partition, message });
          resolveOffset(message.offset); await heartbeat();
        }
      } });
  }
  stop() {
    if (this.stopPromise) return this.stopPromise;
    this.stopped = true;
    this.stopPromise = (async () => { try { await this.consumer.stop(); } finally { await this.consumer.disconnect(); } })();
    return this.stopPromise;
  }
}
