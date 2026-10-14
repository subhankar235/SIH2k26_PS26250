import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const RequestQueue = require('kafkajs/src/network/requestQueue');

test('KafkaJS does not poll an idle queue with a negative timeout on Node24', (t) => {
  const queue = new RequestQueue({ maxInFlightRequests: 1, requestTimeout: 3000, enforceRequestTimeout: true,
    clientId: 'compatibility-test', broker: 'localhost:29092', logger: { debug() {}, error() {} } });
  t.after(() => queue.destroy());
  queue.scheduleCheckPendingRequests();
  assert.equal(queue.throttleCheckTimeoutId, null, 'An idle queue must not start a perpetual timer.');
});
