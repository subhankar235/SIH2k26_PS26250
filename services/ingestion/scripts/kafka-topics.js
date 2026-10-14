import kafkajs from 'kafkajs';
import { loadConfig } from '../src/config.js';
import { TOPICS } from '../src/contracts.js';
const config = loadConfig();
if (!config.kafka.brokers.length) throw new Error('Set KAFKA_BROKERS before creating topics.');
const kafka = new kafkajs.Kafka({ ...config.kafka, clientId: 'logistics-topic-setup',
  logLevel: kafkajs.logLevel.NOTHING, retry: { retries: 3 } });
const admin = kafka.admin();
try {
  await admin.connect();
  await admin.createTopics({ waitForLeaders: true, topics: Object.values(TOPICS).map((topic) => ({
    topic, numPartitions: 3, replicationFactor: 1, configEntries: [{ name: 'retention.ms', value: String(config.retentionDays * 86400000) }],
  })) });
  console.log('Five logistics topics exist. Existing topic settings are not overwritten.');
} finally { await admin.disconnect(); }
