# Air Power — Backend Guide (Structure + Steps)

Covers everything except the dashboard: FastAPI backend, Kafka streaming, ML, optimisation, simulation, evaluation, and data. All data is synthetic and non-operational.

---

## 1. Backend Scope

| Module | Folder | Features |
|---|---|---|
| API + services | `backend/` | F1–F10 |
| Streaming | `streaming/` | F1 |
| ML models | `ml/` | F1, F2, F3, F4 |
| Optimisation | `optimisation/` | F5, F6 |
| Simulation | `simulation/` | F7 |
| Evaluation | `evaluation/` | F10 |
| Synthetic data | `data/` | All |

**Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, Apache Kafka, NetworkX, PyMC, PyTorch, GPyTorch, OR-Tools, `alns`, SimPy, Hypothesis, LangGraph, MLflow, Pytest.

---

## 2. Folder Structure

```
backend/
├── pyproject.toml
├── Dockerfile
├── alembic.ini
├── .env.example
├── app/
│   ├── main.py
│   ├── core/            # config, logging, security, exceptions, deps
│   ├── db/
│   │   ├── session.py
│   │   ├── base.py
│   │   ├── models/      # record, claim, decision, forecast, schedule,
│   │   │                # experiment, agent_run, approval, audit_log
│   │   └── migrations/
│   ├── schemas/         # Pydantic: ingestion, evidence, validity, forecast,
│   │                    # planning, stress, agents, verification, audit, benchmarks
│   ├── api/
│   │   ├── router.py
│   │   └── v1/          # health, ingestion, evidence, validity, forecasts,
│   │                    # planning, replanning, stress, agents,
│   │                    # verification, approvals, audit, benchmarks
│   ├── services/
│   │   ├── ingestion/     # validator, normaliser, deduplicator, entity_matcher
│   │   ├── evidence/      # contradiction_detector, staleness_checker,
│   │   │                  # provenance_tracer, evidence_graph, uncertainty, autopsy
│   │   ├── validity/      # dependency_graph, assumption_tracker,
│   │   │                  # change_detector, reverifier, status
│   │   ├── forecasting/   # features, predictor, calibration
│   │   ├── planning/      # problem_builder, solver_service, comparator
│   │   ├── replanning/    # diff_inputs, impact_analysis,
│   │   │                  # incremental_recompute, schedule_diff
│   │   ├── stress/        # run_manager
│   │   ├── explanation/   # explainer
│   │   ├── verification/  # constraint_checker, consistency_checker,
│   │   │                  # uncertainty_flagger, approval_router
│   │   ├── audit/         # audit_service
│   │   └── benchmarking/  # results_service
│   ├── agents/          # graph, state, routing, checkpointing, retry,
│   │                    # human_approval, nodes/, prompts/
│   └── utils/
└── tests/               # unit/, integration/, api/, conftest.py

streaming/               # config/, producers/, consumers/, utils/, tests/
ml/                      # entity_matching/, temporal_graph/, bayesian/,
                         # change_point/, forecasting/, artifacts/, common/
optimisation/            # models/, cpsat/, alns/, incremental/, benchmarks/
simulation/              # twin/, faults/, scenarios/, runner/, properties/
evaluation/              # baselines/, ablations/, metrics/, stats/, experiments/, reports/
data/                    # generators/, schemas/, samples/, raw/, processed/
infra/                   # docker/, postgres/, kafka/, mlflow/
```

---

## 3. Step-by-Step Backend Build

### Step 1 — Environment

```bash
mkdir air-power && cd air-power
git init
python -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings \
  sqlalchemy alembic psycopg2-binary pytest pytest-cov httpx \
  networkx pandas numpy scipy mlflow
```

### Step 2 — Infrastructure (Docker Compose)

Services: `postgres`, `kafka` (KRaft or with zookeeper), `mlflow`.

```bash
cp .env.example .env
docker compose up -d postgres kafka mlflow
bash infra/kafka/create_topics.sh   # resource, crew, availability, weather, constraint, dead_letter
```

### Step 3 — Synthetic Data (do this before models)

Files in `data/generators/`: `generate_resources.py`, `generate_crew.py`, `generate_availability.py`, `generate_weather.py`, `generate_constraints.py`, `generate_all.py`, `make_splits.py`.

Requirements:
- Every generator accepts `--seed` and `--size`.
- Save **ground-truth labels** for injected faults: stale, missing, duplicate, conflict.
- Use **time-based** train/val/test splits.

```bash
python data/generators/generate_all.py --seed 42 --size 10000
python data/generators/make_splits.py --seed 42
```

### Step 4 — FastAPI Core

Create `app/main.py`, `app/core/config.py` (Pydantic Settings), `app/core/logging.py`, `app/db/session.py`.

```python
# app/main.py
from fastapi import FastAPI
from app.api.router import api_router

app = FastAPI(title="Air Power API", version="1.0.0")
app.include_router(api_router, prefix="/api/v1")
```

```bash
uvicorn app.main:app --reload --port 8000
```

Add `GET /api/v1/health`.

### Step 5 — Database Models and Migrations

Create ORM models for: `source`, `raw_event`, `record`, `claim`, `issue`, `evidence_edge`, `decision`, `assumption`, `dependency`, `forecast`, `schedule`, `agent_run`, `verification_result`, `approval`, `audit_entry`, `experiment_run`.

Rules:
- Store both `event_time` and `ingest_time`.
- Version records, forecasts, schedules, and decisions.
- No hard deletes; use supersession and flags.
- Unique constraint on (`source_id`, `source_event_id`) for idempotency.

```bash
alembic init app/db/migrations
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

### Step 6 — Pydantic Schemas

One file per domain in `app/schemas/`. Use a consistent error schema: `{code, message, details}`.

### Step 7 — F1 Ingestion + Kafka

**Producer** (`streaming/producers/synthetic_producer.py`): replay generated data into topics.

**Consumer** (`streaming/consumers/ingestion_consumer.py`) pipeline:

```
consume → validate (Pydantic) → normalise → timestamp → dedupe → store
                    └── invalid/conflicting → dead_letter + flagged (never dropped)
```

Services: `validator.py`, `normaliser.py`, `deduplicator.py` (deterministic keys first), `entity_matcher.py` (Ditto added in Step 11).

Endpoints:
- `POST /ingestion/events`
- `GET /ingestion/status`
- `GET /ingestion/flagged`

```bash
python streaming/producers/run_producer.py --topic resource
python streaming/consumers/run_consumer.py
```

**Check:** replay of 10k records → zero duplicates; all invalid records flagged with reasons.

### Step 8 — F9 Verification + Audit (build early)

| File | Job |
|---|---|
| `constraint_checker.py` | Capacity, time windows, precedence, policy. **Must not import solver code.** |
| `consistency_checker.py` | Schedule vs forecast vs evidence versions |
| `uncertainty_flagger.py` | High uncertainty, unresolved conflicts, uncertain validity |
| `approval_router.py` | Routes to human queue |
| `audit_service.py` | Append-only audit trail |

Outcomes: `verified`, `invalid`, `uncertain` (+ violations list).

Endpoints:
- `POST /verification/check`, `GET /verification/{id}`
- `GET /approvals`, `POST /approvals/{id}/decision`
- `GET /audit`, `GET /audit/{entity}/{id}` (read-only; no update/delete)

**Check:** corrupted schedules are always rejected; audit entries cannot be modified.

### Step 9 — F5 Planning (CP-SAT + ALNS)

```bash
pip install ortools alns
```

`optimisation/`:
- `models/problem.py`, `solution.py`
- `cpsat/model_builder.py`, `constraints/{resource_capacity,time_windows,precedence,policy}.py`, `objectives.py`, `solver.py`
- `alns/{destroy_operators,repair_operators,hybrid,runner}.py`

Objectives: makespan, cost, lateness, robustness.

Minimal CP-SAT pattern:

```python
from ortools.sat.python import cp_model

model = cp_model.CpModel()
start = {t: model.NewIntVar(0, horizon, f"s_{t}") for t in tasks}
# add capacity, window, precedence constraints...
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30
solver.parameters.random_seed = seed
status = solver.Solve(model)
```

Service layer: `problem_builder.py`, `solver_service.py`, `comparator.py`.

Endpoints:
- `POST /planning/solve`
- `GET /planning/schedules/{id}`
- `GET /planning/alternatives`

Every schedule passes Step 8 verification before acceptance.

### Step 10 — F2 Evidence Intelligence (USP 1)

Build the **rule-based baseline first**:
- `staleness_checker.py` — per-type freshness thresholds
- `contradiction_detector.py` — conflicting claims across sources
- `evidence_graph.py` — NetworkX graph (claims, sources, entities, time)
- `provenance_tracer.py` — origin + version chain
- `autopsy.py` — Contradiction Autopsy report (competing claims, sources, timestamps, history, missing info, uncertainty)

PyMC reliability (`ml/bayesian/`): fit source-reliability posterior, check convergence, save.

Endpoints:
- `GET /evidence/issues`
- `GET /evidence/issues/{id}/autopsy`
- `GET /evidence/provenance/{record_id}`

### Step 11 — ML Training (Ditto, TGN, StrGNN)

```bash
pip install torch
```

| Model | Files | Command |
|---|---|---|
| Ditto | `ml/entity_matching/{ditto_model,train,infer}.py`, `configs/ditto.yaml` | `python ml/entity_matching/train.py --config ml/entity_matching/configs/ditto.yaml --seed 42` |
| TGN | `ml/temporal_graph/tgn/{model,train}.py` | `python ml/temporal_graph/tgn/train.py --config ml/temporal_graph/configs/tgn.yaml --seed 42` |
| StrGNN | `ml/temporal_graph/strgnn/{model,train}.py` | `python ml/temporal_graph/strgnn/train.py --config ml/temporal_graph/configs/strgnn.yaml --seed 42` |

Shared: `ml/temporal_graph/dataset.py`, `evaluate.py`, `ml/common/{seed,mlflow_utils}.py`.

Rules:
1. Seed everything; train with multiple seeds.
2. Time-based splits.
3. Log params, metrics, artifacts to MLflow.
4. Compare against rule-based baselines; **adopt a model only if it wins**.
5. Low-confidence Ditto matches are flagged, not auto-merged.

### Step 12 — F3 Decision Validity (USP 2)

| File | Job |
|---|---|
| `dependency_graph.py` | NetworkX DAG: input versions + assumptions → decisions |
| `assumption_tracker.py` | Stores each decision's validity envelope |
| `change_detector.py` | Wraps BOCPD (`ml/change_point/bocpd.py`, `hazard.py`) |
| `status.py` | One of `verified`, `stale`, `invalidated`, `uncertain`; logs transitions to audit |
| `reverifier.py` | Traverse graph → re-verify only affected decisions |

BOCPD is tuned (hazard rate, priors), not trained.

Endpoints:
- `GET /validity/decisions`, `GET /validity/decisions/{id}`
- `POST /validity/reverify`

**Check:** incremental statuses equal full-recompute statuses, with fewer nodes touched on local changes.

### Step 13 — F4 Prediction + Uncertainty

```bash
pip install gpytorch
```

1. `services/forecasting/features.py` — lag, rolling, calendar, weather features.
2. **Baselines first:** `ml/forecasting/baselines/{arima,lstm,sparse_gp}.py`.
3. **DS-DGP:** `ml/forecasting/ds_dgp/{model,train}.py`, `configs/ds_dgp.yaml`.
4. `ml/forecasting/calibration.py` — coverage, ECE, NLL (target: 90% interval coverage within ±5 points).
5. `services/forecasting/predictor.py` — versioned forecasts linked to input versions; flag high uncertainty.

```bash
python ml/forecasting/baselines/arima.py --seed 42
python ml/forecasting/ds_dgp/train.py --config ml/forecasting/configs/ds_dgp.yaml --seed 42
```

Endpoints: `POST /forecasts`, `GET /forecasts/{id}`.

### Step 14 — F6 Replanning + Change Impact

| File | Job |
|---|---|
| `diff_inputs.py` | Exact input changes between versions |
| `impact_analysis.py` | Affected elements via F3 graph |
| `incremental_recompute.py` | Warm start / partial re-solve (`optimisation/incremental/`) |
| `schedule_diff.py` | Added / removed / moved / unchanged assignments |

Fall back to full re-solve if feasibility can't be guaranteed. Verify the result with F9.

Endpoints: `POST /replanning/run`, `GET /replanning/diff/{old}/{new}`.

### Step 15 — F8 Agentic Layer (LangGraph)

```bash
pip install langgraph langchain-core
```

| File | Job |
|---|---|
| `agents/state.py` | Typed Pydantic state |
| `agents/graph.py` | StateGraph definition |
| `agents/nodes/*` | evidence, prediction, change_analysis, optimisation, verification, explanation |
| `agents/routing.py` | INVALID/UNCERTAIN → re-analysis; VERIFIED → approval |
| `agents/retry.py` | Bounded retries (default 3), no identical retries |
| `agents/checkpointing.py` | Postgres checkpointer |
| `agents/human_approval.py` | Interrupt/resume |

Rules:
- Agents **cannot** override F9 validators.
- Explanations must cite evidence (record IDs, versions, validator results).
- Agent I/O is schema-validated; schema failure counts as a retry.

Endpoints: `POST /agents/requests`, `GET /agents/requests/{id}`, `GET /agents/requests/{id}/explanation`.

### Step 16 — F7 Digital Twin + Stress Lab (USP 3)

```bash
pip install simpy hypothesis
```

- `simulation/twin/{environment,entities,clock}.py`
- `simulation/faults/{missing_data,stale_data,conflicting_data,constraint_change,injector}.py` (seeded)
- `simulation/scenarios/library/*.yaml` — `baseline_clean`, `heavy_staleness`, `source_conflict`, `cascading_changes`
- `simulation/runner/{run_scenario,metrics,mlflow_logger}.py` — detection, false alarms, failure rate, feasibility, recovery
- `simulation/properties/` — Hypothesis tests:
  - invalid results are never accepted
  - same seed → identical run
  - incremental = full

Endpoints: `POST /stress/runs`, `GET /stress/runs/{id}`.

### Step 17 — F10 Benchmarking + Ablations

| Folder | Contents |
|---|---|
| `evaluation/baselines/` | `naive_pipeline`, `rule_based_only`, `full_recompute` |
| `evaluation/ablations/` | no F2, no F3, no uncertainty, no ALNS, no F9 |
| `evaluation/metrics/` | latency, feasibility, error_detection, false_alarms, recovery, calibration |
| `evaluation/stats/` | Wilcoxon / t-test, bootstrap CIs, effect sizes |
| `evaluation/experiments/` | evidence detection, incremental vs full, forecast calibration, hybrid solver, end-to-end stress |

```bash
bash scripts/run_benchmarks.sh
python evaluation/reports/generate_report.py
```

Endpoints: `GET /benchmarks/results`, `GET /benchmarks/ablations`.

### Step 18 — Testing

| Level | Location | Tool |
|---|---|---|
| Unit | `backend/tests/unit/` | Pytest |
| Integration | `backend/tests/integration/` | Pytest + test DB/Kafka |
| API | `backend/tests/api/` | Pytest + httpx/TestClient |
| Property | `simulation/properties/` | Hypothesis |
| E2E | `tests/e2e/` | Pytest + Docker Compose |
| Contract | `tests/contract/` | TS types ↔ Pydantic parity |

```bash
pytest --cov=app
ruff check . && black --check . && mypy app
```

### Step 19 — Dockerise

```bash
docker compose up --build
```

Dockerfiles for backend, streaming, simulation, mlflow. Add health checks.

---

## 4. Full API Reference

Base path: `/api/v1`

| Area | Endpoints |
|---|---|
| Health | `GET /health` |
| Ingestion | `POST /ingestion/events`, `GET /ingestion/status`, `GET /ingestion/flagged` |
| Evidence | `GET /evidence/issues`, `GET /evidence/issues/{id}/autopsy`, `GET /evidence/provenance/{record_id}` |
| Validity | `GET /validity/decisions`, `GET /validity/decisions/{id}`, `POST /validity/reverify` |
| Forecasts | `POST /forecasts`, `GET /forecasts/{id}` |
| Planning | `POST /planning/solve`, `GET /planning/schedules/{id}`, `GET /planning/alternatives` |
| Replanning | `POST /replanning/run`, `GET /replanning/diff/{old}/{new}` |
| Stress | `POST /stress/runs`, `GET /stress/runs/{id}` |
| Agents | `POST /agents/requests`, `GET /agents/requests/{id}`, `GET /agents/requests/{id}/explanation` |
| Verification | `POST /verification/check`, `GET /verification/{id}` |
| Approvals | `GET /approvals`, `POST /approvals/{id}/decision` |
| Audit | `GET /audit`, `GET /audit/{entity}/{id}` |
| Benchmarks | `GET /benchmarks/results`, `GET /benchmarks/ablations` |

**API rules:** consistent error schema, idempotency keys on create/solve, pagination on lists, OpenAPI exported to `docs/api/openapi.json`.

---

## 5. Backend Rules to Remember

1. **Validators are authoritative.** Agents and models are advisory.
2. **Never drop bad data.** Store it and flag it.
3. **Everything is seeded and versioned.**
4. **Incremental by default**, with a full-recompute fallback.
5. **Baselines before advanced models.** Adopt only if they win.
6. **Audit is append-only.**

---

## 6. Backend Build Order (Summary)

```
Env → Infra → Synthetic data → FastAPI core → DB models
→ F1 Ingestion → F9 Verification/Audit → F5 Planning
→ F2 Evidence → ML training (Ditto/TGN/StrGNN) → F3 Validity
→ F4 Prediction → F6 Replanning → F8 Agents
→ F7 Stress Lab → F10 Benchmarks → Tests → Docker
```
