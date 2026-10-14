# Logistics ingestion implementation plan

Spec: `docs/logistics-ingestion-design.md`

## Global Constraints

Standalone noncombat administrative logistics ingestion only. All application files under `services/ingestion`. Plain ESM JavaScript on Node 24.19+, npm 11.17.0. Strict schemas, authenticated source bindings, durable SQLite event/projection/outbox transaction, at-least-once Kafka delivery, bounded work, no secrets/payload logging, no weapons/combat planning logic. Original grid application remains outside scope. The design is authoritative. No push or merge.

## Task 1: Contracts and validation

Implement `services/ingestion/src/contracts.js`, `src/errors.js`, `test/contracts.test.js`, and `test/fixtures.js` against the exact envelope/domain definitions in the design. Export `EVENT_TYPES`, `TOPICS`, `eventSchema`, `validateEvent(input,{now})` (now is epoch milliseconds), `canonicalJson(value)`, and `eventSchemas()` (JSON-schema export). `validateEvent` throws `ApiError(422,'VALIDATION_ERROR',message,details)` with bounded field issue details and returns normalized parsed values. `ApiError` exports `(status,code,message,details)` attributes. Normalize all timestamps to UTC; reject invalid dates, unknown fields, nonfinite numbers, unsafe sequences, oversized/duplicate qualifications, invalid ranges, inconsistent capacity, self-destination cargo, and future observations. Export topic maps as frozen values. `eventSchemas()` returns generated JSON schemas (not manually divergent schemas). Tests first: show RED before implementation and GREEN afterward. Fixtures use supplied now to avoid wall-clock flakiness. No subagents. Commit only your four assigned files. Report to the task-specific report path supplied by controller.

## Task 2: Durable core

Controller implements `src/store.js`, `src/ingestion.js`, and focused tests. Contract: `EventStore({path,now,maxPending})`, `acceptBatch(events)` returns ordered receipts, `getEvent`, `listEvents`, `listState`, `listOutbox`, `pending`, `markPublished`, `markFailed`, `retryDead`, `purge`, `metrics`, `close`; `IngestionService` validates/auth-binding before passing to storage. Finish correctness tests before HTTP integration. Match design idempotency, archived stale/expired state, source isolation, transaction rollback, durable restart, bounded backlog, retry and retention semantics. Commit this slice and obtain task review.

## Task 3: HTTP and Kafka integration

Controller implements `src/config.js`, `src/app.js`, `src/server.js`, `src/publisher.js`, focused tests, and source/admin controls. All routes and error codes in design. Safe config validation, bound rate limiter maps, security headers, body/content-type bounds, request IDs, timestamps, health, operational metrics, and bounded shutdown. Kafka disabled mode retains queued work. Topic/key mapping is immutable and server-owned. Drain failure does not falsely acknowledge; dead rows remain visible and admin-retryable. Test real HTTP+SQLite and fake broker fault injection, with separate optional real Kafka test. Commit and obtain task review.

## Task 4: Documentation, demo, and final verification

Controller adds README, `.env.example` without usable secrets, credential generator, deterministic demo CLI, Dockerfile, broker Compose, OpenAPI contract, and schema/sample event artifacts. Explain middleware and Kafka learning path. Root package scripts run check, test, coverage, demo, and optional Kafka integration. Commit lockfile and install with lifecycle scripts disabled. Run appropriate tests/check/audit; smoke-test real API. Run real-broker integration only when available; report environmental gaps accurately. Independent final whole-branch review, fix findings, commit verified final changes, and record final state in ledger.
