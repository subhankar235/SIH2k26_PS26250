# Civilian logistics decision-support system

The maintained application is [services/ingestion](services/ingestion/README.md). It includes JavaScript ingestion, durable Kafka delivery, a read-only dashboard, bounded civilian relief optimization, automatic replanning, deterministic negotiating agents, synthetic demand forecasting and optional local model annotations.

## Run locally

Use Node.js 24.19.0 or later and npm 11.17.0. From this directory:

```powershell
cd services/ingestion
npm ci --ignore-scripts
npm run setup
npm run credentials
npm start
```

The credential generator refuses to overwrite an existing `.env`; skip it if credentials already exist. Open `http://127.0.0.1:3100/monitor/` with the separate viewer token. In another terminal in the same service directory, run `npm run relief:dynamic` for the event-driven demonstration.

## Repository layout

- `services/ingestion/src/`: API, SQLite persistence, Kafka integration, optimization, models and agent negotiation.
- `services/ingestion/web/`: browser dashboard.
- `services/ingestion/test/` and `integration/`: unit, HTTP and Kafka tests.
- `services/ingestion/scripts/`: setup, demos, training and browser/pipeline verification.
- `services/ingestion/docs/`: guides, API contracts, examples and validation records.
- `docs/`: design decisions and implementation plans for this system.
- `.github/`: contribution templates and application checks.

Local credentials and databases live under `services/ingestion` and are ignored by Git. Generated test databases, logs and screenshots are disposable; validation documents record past results and the scripts reproduce them. The unrelated legacy grid-platform scaffold has been removed from this worktree; earlier versions remain recoverable from Git history.

## Guides and checks

Start with the [engine guide](services/ingestion/docs/CIVILIAN_ENGINE_GUIDE.md), [dynamic ingestion guide](services/ingestion/docs/DYNAMIC_CIVILIAN_GUIDE.md), and [autonomous negotiation guide](services/ingestion/docs/AUTONOMOUS_NEGOTIATION_GUIDE.md). The service README explains Kafka, optional local inference, authentication and detailed verification.

From `services/ingestion`:

```powershell
npm test
npm run check
npm run contracts:check
```

See [contributing](docs/CONTRIBUTING.md). This remains a bounded fictional civilian demonstrator; it does not implement military operational planning or weapons allocation.
