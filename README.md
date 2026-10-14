# Air Power — administrative event gateway and monitor

The new noncombat administrative logistics system is in [services/ingestion](services/ingestion/README.md). It accepts authenticated maintenance, crew, weather, airport-capacity, and ordinary relief-cargo observations, with durable history, stale-data protection, Kafka delivery, an independent durable Kafka reader, a read-only browser dashboard, data-quality indicators and a finite fictional update simulator. See that module's README for installation, tests, demo, and limitations.

Implementation/design: [ingestion design](docs/logistics-ingestion-design.md), [monitoring modules](docs/logistics-monitoring-plan.md), [module map and demo](services/ingestion/docs/monitoring.md). This work does not implement military operational planning or weapons allocation.

A separate fixed civilian relief engine now demonstrates specialist agents, deterministic optimization and replanning, independent checking, synthetic model training and optional local Gemma/Qwen evidence selectors. Start with the [detailed engine guide](services/ingestion/docs/CIVILIAN_ENGINE_GUIDE.md). Its inputs and outputs are explicitly fictional; it does not plan combat operations.

The earlier grid platform below is historical scaffolding and is not wired into the standalone ingestion module.

## Earlier grid scaffolding

Air Power is a starter platform for monitoring and optimizing a resilient power grid. It combines an operator dashboard, a FastAPI service, event-streaming infrastructure, simulation, forecasting, and optimization modules.

> **Project status:** This repository provides a runnable development foundation. The domain-specific TGN, DS-DGP, Ditto, Bayesian forecasting, and production optimization models are extension points—not trained or production-ready models.

## Quick start

Requirements: Docker Compose v2. From the repository root:

```bash
cp .env.example .env
docker compose up --build
```

Open the dashboard at <http://localhost:3000>, the API docs at <http://localhost:8000/docs>, and the API health endpoint at <http://localhost:8000/health>.

For local Python development, use Python 3.11+:

```bash
python -m venv .venv
# Activate the environment, then:
python -m pip install -e ".[dev]"
uvicorn backend.app.main:app --reload
```

For the frontend, use Node.js 20+:

```bash
cd frontend
npm install
npm run dev
```

## Repository map

- `frontend/` — Next.js operator dashboard
- `backend/` — FastAPI application and core domain types
- `streaming/` — Kafka producer/consumer extension points
- `ml/` — forecasting and graph-model interfaces
- `optimisation/` — dispatch and resilience planning interfaces
- `simulation/` — SimPy digital-twin and fault-injection utilities
- `evaluation/` — benchmark entry points and experiment tracking
- `data/` — reproducible synthetic grid data generation
- `infra/` — container and database infrastructure
- `docs/` — architecture and local development notes
- `tests/` — cross-module checks

See [docs/architecture.md](docs/architecture.md) for component boundaries and [docs/development.md](docs/development.md) for development commands.

## Common commands

```bash
make up          # Start the local Docker Compose stack
make down        # Stop it
make test        # Run Python tests
make lint        # Run Ruff and ESLint
make seed        # Generate sample grid data
make bench       # Run a small synthetic-data benchmark
```

The dashboard and API run without Kafka or MLflow; those services are included in the Compose stack for integration work. Configure local secrets in `.env`—never commit that file.

## License

See [LICENSE](LICENSE).
