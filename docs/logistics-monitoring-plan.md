# Administrative data monitoring modules

## Scope and design

Extend the event gateway with generic, read-only administrative monitoring. This implementation does not allocate aircraft or crews, schedule missions, assess threats, handle weapons, or automate operational decisions. Reported availability is a source assertion, not a readiness determination. Synthetic fixtures represent ordinary relief logistics.

Existing ingestion history, source isolation, outbox ordering and APIs remain authoritative. No LLM is needed to compute facts or quality flags. We considered a fully connected agent graph, a Python orchestration tier, and deterministic event projections: projections offer the clearest reproducibility and smallest failure surface for these modules.

### Contracts

- Monitoring: GET `/monitor/api/snapshot?type=&sourceId=` returns `{generatedAt, scope:{limit:1000,shown,truncated},summary:{total,current,expired,sequenceGaps,disagreements,byType},records,delivery,deliveryScope:'global_outbox'}`. Each record has the ingestion state fields plus `flags` (expired, sequence_gap, source_disagreement, maintenance_date_passed) and `reportedStatus`. Summary counts describe bounded selected records; delivery counts explicitly describe the whole store's outbox, independent of filters. Disagreement compares current same-type/same-entity assertions from different sources; no source is selected as truth.
- Browser: `/monitor/` serves public static UI with no embedded data or secrets. POST `/monitor/session` `{token}` grants a read-only, 30-minute, HttpOnly/SameSite=Strict cookie session. Only a separate optional `MONITOR_VIEWER_TOKEN` grants access; admin/source tokens never grant browser access. POST `/monitor/logout` revokes it. Authenticated GET snapshot is no-store. Login/logout enforce same-origin; loopback HTTP is supported, remote browser use requires HTTPS. Sessions are bounded, in memory, invalidated at restart. Poll snapshots every five seconds with explicit stale/failed status. No writes to ingestion from browser.
- Durable Kafka reader: separate SQLite read-model database, never the ingestion database. Validates envelope/topic/key; processes record + dedupe + projection + broker checkpoint atomically before committing next Kafka offset. Duplicate/reordered/expired messages cannot corrupt latest state. Invalid records are durably quarantined with bounded safe metadata, never raw credentials/content. One database owner per consumer group; local development only. Offset identity includes topic/partition, offsets handled as decimal strings/BigInt. A database failure must not acknowledge messages. No assignments or operational scoring.
- Scenario simulator: local CLI only, bounded predefined fictional updates through existing source APIs. Demonstrates initial facts, weather update, maintenance status change, capacity closure, stale update, duplicate replay, and TTL expiry. No browser execution privileges. Secrets never printed, source/admin authentication unchanged.

### Visual contract

Greenfield administrative console for an analyst on a laptop: quiet, dense information architecture; navy ink, off-white canvas, teal current-state accent, amber review indicators; system sans with monospace IDs; 4px spacing units, 4px corners, restrained borders, no ornamental imagery. Header and summary strip precede a filterable fact table, freshness/quality notes and delivery sidebar. Mobile stacks sections with contained table scrolling. Visible focus, labels, textual states and reduced motion are required. Narrative role is inspection; viewing distance is desktop; temperature is calm; capacity is 100 rows per page from a bounded server snapshot.

## Ordered tasks

1. Root implements monitoring projection adapter, read-only session/API integration, configuration and security tests. Existing APIs stay unchanged; config optional by default.
2. Consumer worker: isolated `src/consumer*.js`, `test/consumer*.test.js`, `integration/consumer*.test.js`, CLI and consumer-specific docs. No edits to app/config/store/package unless coordinated with root. Use existing Kafka adapter config, pinned dependencies and canonical validators.
3. Dashboard: isolated `web/*` vanilla HTML/CSS/ESM, no CDN/build/runtime dependencies. Implements above browser contracts, provenance inspector, filters, local pagination, JSON download, timestamps, empty/loading/error/login/logout states. Safe DOM text only; no HTML from event data.
4. Root implements simulator, integration wiring, generated API docs, README/runbook/architecture decisions, quality checks. Test real Docker Kafka, native service, browser and non-root image where relevant.
5. Independent task and final reviews; address findings and rerun scoped checks. Commit on existing isolated feature branch only; no merge/push/deploy.

## Quality constraints

No skipped tests, disabled warnings, secret output, fake data labelled live, source authority guesses, unbounded polling overlap, writable browser credentials, or at-least-once labelled exactly-once. SQLite is single-owner/local, not HA. Consumer broker offsets are durable before ack; quarantine has bounded retention/capacity. Dashboard data is explicitly bounded and report-only. Required checks: deterministic boundary tests, auth/CSRF/no-cache/input checks, existing tests unchanged, actual Kafka restart/replay smoke and browser interaction checks.
