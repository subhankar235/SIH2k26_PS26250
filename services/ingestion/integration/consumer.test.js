import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import kafkajs from 'kafkajs';
import { ConsumerStore } from '../src/transport/consumer-store.js';
import { createKafkaConsumer, KafkaReadModelWorker } from '../src/transport/consumer.js';
import { TOPICS } from '../src/contracts/events.js';
import { event } from '../test/fixtures.js';

async function until(predicate) {
  const end = Date.now() + 25000;
  while (!predicate()) {
    if (Date.now() > end) throw new Error('Consumer integration timeout.');
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

test('real Kafka consumer survives restart and broker rewind with durable replay and quarantine', { timeout: 70000 }, async (t) => {
  assert.ok(process.env.KAFKA_TEST_BROKERS, 'Set KAFKA_TEST_BROKERS to a local test Kafka broker.');
  const brokers = process.env.KAFKA_TEST_BROKERS.split(',');
  const { Kafka, logLevel } = kafkajs;
  const kafka = new Kafka({ clientId: 'consumer-smoke', brokers, logLevel: logLevel.NOTHING });
  const admin = kafka.admin(); const producer = kafka.producer({ allowAutoTopicCreation: false });
  const folder = mkdtempSync(join(tmpdir(), 'consumer-kafka-')); const groupId = `consumer-smoke-${randomUUID()}`;
  const options = { path: join(folder, 'reader.sqlite'), groupId };
  const config = { brokers, ssl: false, requestTimeout: 5000 };
  let store; let worker; let crash = false;
  t.after(async () => {
    try { if (worker) await worker.stop(); } finally {
      store?.close(); await producer.disconnect(); await admin.disconnect(); rmSync(folder, { recursive: true, force: true });
    }
  });
  await admin.connect(); await producer.connect();
  await admin.createTopics({ waitForLeaders: true, topics: Object.values(TOPICS).map((topic) => ({ topic, numPartitions: 3, replicationFactor: 1 })) });
  const first = event({ sourceId: 'consumer-smoke', entityId: randomUUID() }); const topic = TOPICS[first.type];
  const key = `${first.sourceId}:${first.entityId}`;
  await producer.send({ topic, acks: -1, messages: [{ partition: 0, key, value: JSON.stringify(first) }] });
  store = new ConsumerStore(options);
  worker = new KafkaReadModelWorker({ store, consumer: createKafkaConsumer(config, groupId), onFailure: () => { crash = true; } });
  await worker.start();
  const ownEvents = () => store.db.prepare('SELECT * FROM consumer_events WHERE source_id=? AND entity_id=?').all(first.sourceId, first.entityId);
  await until(() => crash || ownEvents().length === 1); assert.equal(crash, false);
  await worker.stop(); store.close();
  // Deliberately rewind Kafka to exercise DB checkpoints, rather than merely trusting group offsets at restart.
  await admin.setOffsets({ groupId, topic, partitions: [{ partition: 0, offset: '0' }] });
  const second = event({ sourceId: first.sourceId, entityId: first.entityId, sequence: 2, data: { status: 'maintenance' } });
  const [sent] = await producer.send({ topic, acks: -1, messages: [
    { partition: 0, key, value: JSON.stringify(first) },
    { partition: 0, key, value: JSON.stringify(second) },
    { partition: 0, key: 'secret-marker', value: '{"secret-marker":' },
  ] });
  const finalOffset = (BigInt(sent.baseOffset) + 3n).toString();
  store = new ConsumerStore(options);
  worker = new KafkaReadModelWorker({ store, consumer: createKafkaConsumer(config, groupId), onFailure: () => { crash = true; } });
  await worker.start();
  await until(() => crash || BigInt(store.checkpoint(topic, 0) ?? '0') >= BigInt(finalOffset));
  assert.equal(crash, false); assert.equal(ownEvents().length, 2);
  const latest = store.db.prepare(`SELECT e.event_json FROM consumer_latest p JOIN consumer_events e ON e.id=p.event_cursor
    WHERE p.source_id=? AND p.entity_id=?`).get(first.sourceId, first.entityId);
  assert.equal(JSON.parse(latest.event_json).eventId, second.eventId);
  const quarantined = store.quarantined({ limit: 1000 });
  assert.ok(quarantined.some((item) => item.topic === topic && item.offset === (BigInt(sent.baseOffset) + 2n).toString() && item.reason === 'INVALID_JSON'));
  assert.doesNotMatch(JSON.stringify(quarantined), /secret-marker/);
  await worker.stop();
  const committed = await admin.fetchOffsets({ groupId, topics: [topic] });
  assert.ok(BigInt(committed[0].partitions.find((item) => item.partition === 0).offset) >= BigInt(finalOffset));
});
