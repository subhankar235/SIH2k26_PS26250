# Architecture

```text
Next.js dashboard ──HTTP──> FastAPI ──> grid domain services
                                  ├──> PostgreSQL (assets/events)
                                  ├──> Kafka (telemetry stream)
                                  └──> MLflow (experiment tracking)

Synthetic data ──> simulation / model evaluation ──> dispatch optimization
```

The dashboard talks to the versioned `/api/v1` API. API schemas are defined in `backend/app/schemas.py`; shared immutable asset types live in `backend/core`. Streaming, ML, optimization, and simulation are kept as separate packages so they can be developed and tested independently. The current summary endpoint is a static demonstration response and should be replaced with repository-backed operational data when persistence and ingestion are implemented.

## Planned model and solver boundaries

- Graph and temporal models (TGN, DS-DGP, Ditto) consume time-indexed asset and network observations.
- PyMC probabilistic models expose uncertainty intervals rather than point estimates only.
- Optimization consumes forecasts and constraints, then produces a dispatch/restoration plan.
- SimPy scenarios generate normal-operation and fault-injection traces for reproducible evaluation.
- MLflow records model parameters, data version, metrics, and artifacts.
