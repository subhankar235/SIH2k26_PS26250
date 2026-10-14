# Administrative logistics ingestion

Date: 2026-10-15

## Purpose and scope

Build a standalone JavaScript API for noncombat aircraft-maintenance, crew-availability, weather, airport-capacity, and ordinary relief-cargo events. It provides authenticated ingestion, durable event history, source-specific latest state, and asynchronous Kafka delivery. It does not plan operations, allocate weapons, process adversary intelligence, or make aircraft assignments.

The existing electrical-grid application is outside this module. All new application files live in `services/ingestion`. The user requested immediate implementation and delegated routine technology choices; this document records the chosen defaults.

## Runtime and boundaries

- Node.js 24.19+; ESM JavaScript; npm 11.17.0; Express 5, Zod 4, KafkaJS, Helmet.
- SQLite (`node:sqlite`) provides a transactional local event store and outbox. Deployment is one service process per database file, on a local filesystem. This is a runnable development and small-deployment foundation, not a multi-replica production certification. SQLite's Node API stability is documented in the README.
- Kafka is optional at startup. Accepted events remain durably queued when it is unavailable. No console sink may falsely mark them published.
- HTTP binds to loopback by default. Secrets are supplied through environment configuration and never committed. TLS termination is a deployment requirement for remote access.
- No external data-provider fetching, public internet scraping, arbitrary URL requests, LLM calls, or personal names/contact details.

## Contract

Envelope fields: `schemaVersion` (literal 1), `eventId` (UUID), `sourceId`, `type`, `entityId`, `sequence` (positive safe integer), `observedAt`, `validUntil`, and `data`. Identifiers match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. All objects are strict. Dates require RFC3339 timestamps with timezone, are normalized to UTC, and must describe real dates. `validUntil` must exceed `observedAt` by at most seven days. Reject observations over 60 seconds in the future. Expired historical records can be archived but cannot update current state.

Event types and exact data fields:

- `aircraft.status`: `status` = available/maintenance/unavailable, `airportId`, `capacityKg` (0..1,000,000), optional `maintenanceDueAt` timestamp.
- `crew.availability`: `status` = available/unavailable/rest, `qualifications` (unique identifier array, 1..16), `availableFrom`, `availableUntil` timestamps; until must exceed from.
- `weather.observation`: `temperatureC` (-100..60), `windSpeedMps` (0..150), `visibilityM` (0..100,000), `condition` = clear/rain/fog/snow/storm.
- `airport.capacity`: `status` = open/restricted/closed, `arrivalsPerHour`, `departuresPerHour` (integers 0..1,000); closed requires both zero.
- `cargo.request`: `category` = medical/food/water/equipment, `massKg` (>0..1,000,000), `originAirportId`, `destinationAirportId` (different), `requestedDeliveryBy` timestamp, `temperatureControlled` boolean.

Source bindings come from `INGESTION_SOURCES_JSON`: array of `{sourceId, token, types}`. Tokens are at least 32 characters, are unique, and are compared using hashes and constant-time comparison. A separate admin bearer token protects all read, metrics, replay, retention, and outbox-control routes. Health returns minimal information without authentication. Payload `sourceId` and `type` must match the authenticated source's configured permissions.

## Correctness and delivery

- Each validated event is normalized and canonically hashed. Exact retries return the original receipt; reuse of an event ID with different content returns conflict. Cross-source event-ID collisions must not expose another source's data.
- Latest state is isolated by `(sourceId,type,entityId)`. Sequences from different sources are never compared.
- Lower/equal sequences or an observation older than the current projection are archived as stale. Expired records are archived as expired. Neither updates the projection or enters the delivery outbox. Sequence gaps are recorded as quality warnings, not fabricated into missing events.
- Entire batches (1..100 events) commit atomically. Any validation, authorization, conflict, or durable backlog-capacity failure rolls back the entire batch. Backlog limit is checked against net newly queued events, not duplicates/stale records.
- Event insert, latest projection, and outbox insert are one SQLite transaction. A successful HTTP receipt means persisted, not delivered to Kafka.
- An outbox worker sends bounded batches sequentially, only marks a row delivered after acknowledgement, retries using bounded exponential delay, and dead-letters after configurable attempts. It prevents concurrent flushes in one process. Manual retry is admin-only and audited. At-least-once delivery means consumers must deduplicate by event ID; a crash after acknowledgement can cause a duplicate.
- Topic mapping is server-owned: `logistics.aircraft.v1`, `logistics.crew.v1`, `logistics.weather.v1`, `logistics.airport.v1`, `logistics.cargo.v1`. Key is source ID plus entity ID. No cross-topic ordering guarantee.
- Source-specific projections have explicit freshness; expired state is returned as expired rather than represented as current. Historical replay reads immutable history using bounded cursor pagination and filters; it never changes projections or creates outbox messages.
- Retention removes only records older than the configured retention period with no queued/dead outbox work and not referenced by current projections. Pending/dead events are never silently dropped. Pagination tolerates retained/deleted IDs.

## HTTP routes

- `GET /health/live`, `GET /health/ready`: minimal liveness and local-store readiness. Kafka status is a separate admin diagnostic; broker outage does not prevent durable acceptance while capacity remains.
- `POST /v1/events`, `POST /v1/events/batch`: source-authenticated writes. Single receipt 201 (new) / 200 (duplicate); atomic batch 200 with ordered receipts.
- `GET /v1/events`: admin historical pagination by `after` numeric cursor, `limit` 1..100, optional source/type/entity filters.
- `GET /v1/events/:eventId`: admin receipt/history lookup.
- `GET /v1/state`: admin paginated source-specific state with freshness.
- `GET /v1/outbox`: admin paginated status metadata, not secret payload dumps.
- `POST /v1/outbox/:eventId/retry`: admin retry of dead work only.
- `POST /v1/outbox/flush`: admin bounded drain; reports unavailable when Kafka is disabled.
- `POST /v1/retention`: admin bounded retention purge.
- `GET /v1/metrics`: admin operational counters and outbox counts, no tokens or personal data.
- `GET /v1/schema`: admin JSON schemas generated from the same Zod contracts.

All error responses use `{error:{code,message,details?},requestId}`. Malformed JSON=400, authentication=401, source authorization=403, missing=404, conflict=409, body too large=413, unsupported content type=415, schema/query validation=422, rate limit=429, backlog/broker unavailable=503, internal=500 with no internals. Unknown API paths also use this contract. Body limit 256 KiB; all pagination and batches bounded; public endpoint rate limits bounded by IP and source writes bounded by source. No permissive CORS, no payload/token logging, trust proxy off by default. Configure request timeouts and graceful shutdown.

## Threat model

Untrusted boundaries: HTTP headers/body/query, Kafka acknowledgements, local configuration, and local database files. Assets: source authenticity, immutable event history, state ordering, bearer credentials, and pending delivery. Abuse tests cover spoofed source/type, malicious fields, oversized bodies, invalid dates/numbers, duplicate conflicts, batch rollback, expired/stale state, offline brokers, false acknowledgements, metadata disclosure, and unauthenticated admin access. Tokens and data files are ignored by git. Dependency installation disables scripts and the lockfile is audited.

## Verification and limitations

Use Node's built-in test runner with pure contract tests, real SQLite persistence tests, HTTP tests against a localhost server, and an explicit Kafka adapter integration test. Test restart persistence, rollback, delivery failures and retries, duplicate semantics, retention, and freshness with injected clocks. Include a separate real-broker test enabled by `KAFKA_TEST_BROKERS`; never call fake-adapter tests real Kafka validation. Docker Compose provides a local broker when Docker is available.

Document installation, credential generation, configuration, sample requests, a reproducible demo, the outbox consistency model, schema/topic contracts, middleware teaching notes, and remaining deployment requirements. No claim of production certification, exactly-once delivery, real aircraft validation, or achieved throughput without measurements.
