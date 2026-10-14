# ADR: Standalone transactional ingestion with an asynchronous outbox

Status: Accepted for this local/single-process implementation

Date: 2026-10-15

## Context

The user requested immediate JavaScript ingestion implementation, with Python computation possible later, and permitted omitting the existing grid-specific application. We need inspectable source-authorised events and a runnable module that continues accepting within a bounded backlog when Kafka is unavailable. There is no requirement for multiple replicas or a certified operational deployment in this increment.

## Decision

Use a standalone Express5 service with Zod4 validation and an immutable event history, source-specific latest-state references, and an outbox in one SQLite transaction. Use Node24.19's native SQLite API to avoid a native addon and make local startup independent of a database server. Kafka delivery is asynchronous and at least once. No LLM sits in the ingestion path.

Use separate source credentials and type allowlists. Store bearer-token hashes in runtime configuration; supply credentials through ignored local files or deployment environment secrets. Admin reads and delivery controls require a separate credential. Structured error responses and low-information logs keep credentials and payloads outside telemetry.

## Alternatives

- Direct HTTP-to-Kafka publishing cannot atomically acknowledge local state and remote delivery without additional coordination. It would couple acceptance to broker availability.
- Memory-only state is easy to demonstrate but loses history and pending work on restart.
- PostgreSQL is a suitable future choice for multiple service replicas. This increment selects SQLite to deliver a locally runnable transactional module; PostgreSQL requires a separate concurrency/lease/migration and shared-limiter design.
- Unrestricted JSON topics are flexible but make downstream contracts and authorisation difficult to validate. We chose five strict observation domains.

## Consequences

Operate one process per SQLite file, on a local filesystem. Idempotency is bounded by retained event history. Source-specific observations remain separate until an explicit authority/reconciliation policy is designed. Consumers need event-ID deduplication and source-specific ordering/freshness checks. Terminal dead work is visible and consumes backlog capacity.

KafkaJS2.2.4 requires a checksum-verified local idle-queue patch on the tested Node24 runtime. The explicit setup script is part of the installation contract; upgrades must revalidate it. The local Kafka image and plaintext loopback listener are development choices, not remote deployment defaults.

## Future module boundaries

Permitted follow-on work can include provider adapters for authorised noncombat data, data-quality reconciliation, maintenance/readiness administration, ordinary transport logistics simulations, and a read-only monitoring UI. Flight assignment, weapons allocation, adversary analysis, and combat retasking are not implemented by this module.
