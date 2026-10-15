# Reading and extending the JavaScript ingestion service

Start with `src/app.js`, then `src/ingestion/service.js`, then `src/ingestion/store.js`. These separate HTTP handling, domain validation/authorisation, and durable storage.

## Follow a request

1. Express receives the request. The first middleware creates a request ID and observes completion without logging the body or credentials.
2. Helmet applies security headers. The bounded IP limiter runs before authentication and body parsing.
3. The route authenticates a source bearer token. Tokens are hashed and compared with constant-time comparison; the matching source's permissions become `req.source`.
4. Content-type middleware requires JSON. `express.json` parses at most256KiB and rejects compressed requests.
5. The source limiter charges the number of events, so batches do not bypass the event budget.
6. `IngestionService.accept` validates the strict envelope and type-specific data and checks the source/type binding. A valid JSON object is not automatically a valid event.
7. `EventStore.acceptBatch` commits history, latest state, and delivery work together. The returned receipt acknowledges storage. It cannot promise Kafka delivery.
8. Express returns JSON. Errors flow to the final four-argument error middleware; clients receive safe machine-readable codes.

Middleware order matters: authentication before parsing avoids doing expensive work for unauthenticated writers; validation before transactions prevents a partially accepted batch. `next()` passes control to the next middleware. Ending a response stops the normal chain. Async Express5 handler rejections reach error middleware.

## Follow an outgoing event

The HTTP route does not send directly to Kafka. `OutboxPublisher` polls committed delivery work, and `createKafkaAdapter` handles broker connections and acknowledgement. This avoids losing the event when storage succeeds but Kafka is unavailable. Successful asynchronous delivery updates the durable outbox; failed delivery increments attempts and schedules a retry.

Topic names are fixed by the server. Topic partitions divide the stream. The key combines source and entity identity, so that entity stays on the same partition while the partition count remains unchanged. Do not change partition counts without an ordering/migration plan.

Instances in the same consumer group divide partition work. Separate groups can independently receive the same topic: the real integration test uses two groups. Consumers still need durable deduplication and freshness/sequence checks. No consumer that creates a business decision is included in this module.

## Suggested exercises

- Write an HTTP client that reads admin history page by page without printing its bearer token.
- Add a pure, tested conversion from a permitted weather-provider fixture into `weather.observation`, keeping provider credentials outside the payload.
- Reproduce a source-spoofing rejection and explain why valid authentication still results in403.
- Use a fixed test clock to explain why a record can be stored but excluded from current state.
- Inspect a delayed retry and explain why a later event in that same stream waits.

Read the contracts before adding fields. An unknown field is intentionally rejected; a schema extension requires versioning, tests, generated-contract updates, and documentation. Avoid placing provider fetching or scheduling logic into route handlers.

Primary references: [Express middleware](https://expressjs.com/en/guide/using-middleware), [Express errors](https://expressjs.com/en/guide/error-handling), [Node SQLite](https://nodejs.org/api/sqlite.html), [KafkaJS producing](https://kafka.js.org/docs/producing), [Zod API](https://zod.dev/api).
