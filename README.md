# Civilian logistics decision-support system

The maintained application is [services/ingestion](services/ingestion/README.md). It includes JavaScript ingestion, durable Kafka delivery, a read-only dashboard, bounded civilian relief optimization, automatic replanning, deterministic negotiating agents, synthetic demand forecasting and optional local model annotations.

Read the [project blueprint and feature ledger](docs/PROJECT_BLUEPRINT.md) for the original problem statement, brainstorming outcome, adopted decisions and remaining gaps. The [module map](services/ingestion/docs/SYSTEM_MODULES.md) explains the full system; the service directory name is historical.

## Run locally

Use Node.js 24.19.0 or later and npm 11.17.0. From this directory:

```powershell
npm --prefix services/ingestion ci --ignore-scripts
npm run setup
npm run credentials
npm start
```

The credential generator refuses to overwrite an existing service `.env`; skip it if credentials already exist. Open `http://127.0.0.1:3100/monitor/` with the separate viewer token. In another terminal at the repository root, run `npm run demo` for the event-driven demonstration. No root dependency installation is needed.

For an isolated demonstration that needs no server, credentials or broker, run `npm run demo:offline`. It verifies HTTP inputs, negotiation, replanning, dashboard access and database restart, then exits.

## Repository layout

- `services/ingestion/src/`: named contracts, platform, ingestion, transport, planning, agents, forecasting, integrations and dashboard server modules.
- `services/ingestion/dashboard/`: browser dashboard.
- `services/ingestion/test/` and `integration/`: unit, HTTP and Kafka tests.
- `services/ingestion/scripts/`: setup, demos, training and browser/pipeline verification.
- `services/ingestion/docs/`: guides, API contracts, examples and validation records.
- `docs/`: design decisions and implementation plans for this system.
- `.github/`: contribution templates and application checks.

Local credentials and databases live under `services/ingestion` and are ignored by Git. Generated test databases, logs and screenshots are disposable; validation documents record past results and the scripts reproduce them. The unrelated legacy grid-platform scaffold has been removed from this worktree; earlier versions remain recoverable from Git history.

## Guides and checks

Start with the [engine guide](services/ingestion/docs/CIVILIAN_ENGINE_GUIDE.md), [dynamic ingestion guide](services/ingestion/docs/DYNAMIC_CIVILIAN_GUIDE.md), and [autonomous negotiation guide](services/ingestion/docs/AUTONOMOUS_NEGOTIATION_GUIDE.md). The service README explains Kafka, optional local inference, authentication and detailed verification.

From the repository root:

```powershell
npm run verify
npm run test:dashboard
npm run test:pipeline
```

`verify` runs the offline checks. Dashboard fixtures require Python Playwright/Chromium; the pipeline check requires the configured development Kafka broker. See [contributing](docs/CONTRIBUTING.md). This remains a bounded fictional civilian demonstrator; it does not implement military operational planning or weapons allocation.
