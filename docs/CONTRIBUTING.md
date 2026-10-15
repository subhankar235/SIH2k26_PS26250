# Contributing

The application lives in `services/ingestion`. Keep changes scoped to that system; the unrelated legacy grid scaffold has been retired. Root-level design documents explain prior decisions; the service guides describe current behavior.

Use the [module map](../services/ingestion/docs/SYSTEM_MODULES.md) for source locations and the [feature blueprint](PROJECT_BLUEPRINT.md) for decisions/status. The root package delegates to the existing service install; `npm run verify` from the root runs all required offline checks. `npm run demo:offline` runs the isolated integrated journey.

## Setup

Use Node.js 24.19.0+ and npm 11.17.0. From `services/ingestion`, run `npm ci --ignore-scripts`, then `npm run setup`. The setup command applies the explicitly checked KafkaJS compatibility patch. Generate credentials with `npm run credentials` only when no `.env` exists; do not commit credentials, databases, model downloads or local logs.

## Required checks

Run `npm test`, `npm run check` and `npm run contracts:check` from the service directory. Changes to input schemas require `npm run contracts` and a review of the regenerated contract files. The application CI runs these same offline checks.

For browser changes, install Python Playwright/Chromium using the instructions in the service guides, then run the relevant fixture: `scripts/relief-ui-fixture.py`, `scripts/dynamic-ui-fixture.py` or `scripts/negotiation-ui-fixture.py`. Broker and end-to-end changes also require the documented real Kafka pipeline smoke. Local model changes use the separate model smoke. These integration checks have additional local dependencies and are not represented as offline CI coverage.

Retain meaningful assertions and strict validation. Keep source, admin and viewer privileges separate. Preserve atomic ingestion/planning/outbox persistence, deterministic replay, independent plan verification and explicit failure/freshness states.

Document public contract changes and explain what was tested. Generated screenshots, logs, temporary databases and `.superpowers` working notes are disposable artifacts; retain only source fixtures, reproducible scripts and concise validation documents.
