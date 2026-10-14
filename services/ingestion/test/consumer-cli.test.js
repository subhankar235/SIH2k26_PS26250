import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadConsumerConfig } from '../src/consumer-cli.js';

test('consumer config is independent, bounded, and uses a separate database', () => {
  const config = loadConsumerConfig({});
  assert.equal(config.groupId, 'logistics-read-model-v1'); assert.match(config.path, /read-model\.sqlite$/);
  assert.equal(config.maxEvents, 100000); assert.equal(config.maxQuarantine, 1000);
  assert.throws(() => loadConsumerConfig({ CONSUMER_DB_PATH: 'var/events.sqlite' }), /CONSUMER_DB_PATH/);
  for (const env of [{ CONSUMER_GROUP_ID: 'secret\npassword' }, { CONSUMER_MAX_EVENTS: '0' },
    { CONSUMER_MAX_QUARANTINE: '9999999' }, { CONSUMER_MAX_DB_BYTES: '1' }, { CONSUMER_MAX_MESSAGE_BYTES: '1e3' }]) {
    assert.throws(() => loadConsumerConfig(env), /Invalid consumer configuration/);
  }
});
