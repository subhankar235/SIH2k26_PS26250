import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import kafkajs from 'kafkajs';
import { EventStore } from '../src/store.js';
import { createKafkaAdapter, OutboxPublisher } from '../src/publisher.js';
import { TOPICS, validateEvent } from '../src/contracts.js';
import { event } from '../test/fixtures.js';

const { Kafka, logLevel } = kafkajs;
test('real Kafka acknowledges the outbox and two independent groups receive the same event',
  { skip: !process.env.KAFKA_TEST_BROKERS, timeout: 40000 }, async (t) => {
    const brokers = process.env.KAFKA_TEST_BROKERS.split(',');
    const kafka = new Kafka({ clientId: 'logistics-integration', brokers, retry: { retries: 5, initialRetryTime: 100 }, logLevel: logLevel.NOTHING });
    const admin = kafka.admin(); await admin.connect();
    t.after(() => admin.disconnect());
    await admin.createTopics({ waitForLeaders: true, topics: Object.values(TOPICS).map((topic) => ({ topic, numPartitions: 3, replicationFactor: 1 })) });
    const now = Date.now(); const runId = randomUUID();
    const input = validateEvent(event({ sourceId: 'integration-test', entityId: runId }, now), { now });
    const store = new EventStore({ path: ':memory:', now: () => now, maxPending: 10 });
    const publisher = new OutboxPublisher({ store, adapter: createKafkaAdapter({ brokers, ssl: false, requestTimeout: 3000 }) });
    const consumers = []; let timer;
    t.after(async () => { clearTimeout(timer); for (const consumer of consumers) await consumer.disconnect(); await publisher.stop(); store.close(); });
    const received = [[], []]; let complete; let failed;
    const delivery = new Promise((resolve, reject) => {
      complete = resolve; failed = reject;
      timer = setTimeout(() => reject(new Error('Timed out awaiting both Kafka consumer groups.')), 25000);
    });
    // Attach a handler immediately so an asynchronous consumer crash cannot become an unhandled rejection.
    delivery.catch(() => {});
    for (let index = 0; index < 2; index++) {
      const consumer = kafka.consumer({ groupId: `logistics-test-${runId}-${index}` }); consumers.push(consumer);
      consumer.on(consumer.events.CRASH, () => failed(new Error('Kafka test consumer crashed.')));
      await consumer.connect(); await consumer.subscribe({ topic: TOPICS[input.type], fromBeginning: true });
      await consumer.run({ eachMessage: async ({ message }) => {
        const parsed = JSON.parse(message.value.toString());
        if (parsed.eventId !== input.eventId) return;
        received[index].push({ key: message.key.toString(), event: parsed, idHeader: message.headers['event-id'].toString() });
        if (received.every((group) => group.length > 0)) complete();
      } });
    }
    const [receipt] = store.acceptBatch([input]);
    const result = await publisher.flush(); assert.equal(result.published, 1);
    assert.equal(store.getEvent(receipt.eventId).delivery, 'published');
    await delivery;
    for (const group of received) {
      assert.equal(group[0].key, `integration-test:${runId}`);
      assert.equal(group[0].idHeader, input.eventId); assert.deepEqual(group[0].event, input);
    }
    assert.equal(store.acceptBatch([input])[0].duplicate, true);
    assert.equal((await publisher.flush()).attempted, 0);
  });
