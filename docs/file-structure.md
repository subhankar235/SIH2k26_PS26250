# Air Power — Project File Structure

Monorepo layout covering the root, frontend, backend, and all supporting modules (streaming, ML, optimisation, simulation, evaluation, infra). Each folder is tagged with the feature (F1–F10) it implements.

---

## 1. Root Structure

```
air-power/
├── README.md                    # Project overview, setup, how to run
├── LICENSE
├── .gitignore
├── .env.example                 # Template for environment variables
├── .editorconfig
├── .pre-commit-config.yaml      # ruff, black, mypy, eslint hooks
├── Makefile                     # make up / down / test / lint / seed / bench
├── docker-compose.yml           # Local stack: frontend, backend, postgres, kafka, mlflow
├── docker-compose.override.yml  # Dev-only overrides (hot reload, volumes)
├── pyproject.toml               # Python tooling config (ruff, black, pytest, mypy)
│
├── frontend/                    # Next.js + TypeScript dashboard      (see §2)
├── backend/                     # FastAPI + core logic                (see §3)
├── streaming/                   # Kafka producers/consumers           (see §4)
├── ml/                          # Models: TGN, DS-DGP, Ditto, PyMC    (see §5)
├── optimisation/                # OR-Tools CP-SAT + ALNS              (see §6)
├── simulation/                  # SimPy digital twin + fault injection(see §7)
├── evaluation/                  # Benchmarks, ablations, MLflow       (see §8)
├── data/                        # Synthetic datasets & generators     (see §9)
├── infra/                       # Dockerfiles, DB migrations, configs (see §10)
├── docs/                        # Architecture, API docs, diagrams    (see §11)
├── scripts/                     # Helper scripts
│   ├── seed_db.sh
│   ├── generate_synthetic_data.sh
│   ├── run_benchmarks.sh
│   └── wait_for_services.sh
├── tests/                       # Cross-module integration / e2e tests(see §12)
└── .github/
    ├── workflows/
    │   ├── ci-backend.yml       # Pytest + lint + type check
    │   ├── ci-frontend.yml      # Lint + type check + build
    │   └── ci-benchmarks.yml    # Optional scheduled benchmark run
    ├── PULL_REQUEST_TEMPLATE.md
    └── ISSUE_TEMPLATE/
```

---

## 2. Frontend (Next.js + TypeScript + Tailwind + Recharts)

Implements the **dashboard** (Workflow Step 12, Agentic Workflow steps 1 & 8): request submission, results, evidence provenance, uncertainty, audit history, baseline comparisons, human approval.

```
frontend/
├── package.json
├── package-lock.json
├── tsconfig.json
├── next.config.js
├── tailwind.config.ts
├── postcss.config.js
├── .eslintrc.json
├── .env.local.example           # NEXT_PUBLIC_API_URL=...
├── Dockerfile
├── public/
│   ├── favicon.ico
│   └── logo.svg
│
└── src/
    ├── app/                                 # Next.js App Router
    │   ├── layout.tsx
    │   ├── page.tsx                         # Landing / overview dashboard
    │   ├── globals.css
    │   │
    │   ├── ingestion/                       # F1
    │   │   └── page.tsx                     # Stream status, validation errors, flagged records
    │   ├── evidence/                        # F2 · USP 1
    │   │   ├── page.tsx                     # Contradiction list
    │   │   └── [recordId]/page.tsx          # Contradiction Autopsy (provenance timeline)
    │   ├── validity/                        # F3 · USP 2
    │   │   ├── page.tsx                     # Verified / stale / invalidated / uncertain
    │   │   └── [decisionId]/page.tsx        # Validity envelope + dependency graph
    │   ├── forecasts/                       # F4
    │   │   └── page.tsx                     # Forecasts with uncertainty bands
    │   ├── planning/                        # F5 / F6
    │   │   ├── page.tsx                     # Schedules + alternatives
    │   │   └── compare/page.tsx             # Old vs updated schedule diff
    │   ├── stress-lab/                      # F7 · USP 3
    │   │   ├── page.tsx                     # Scenario runner
    │   │   └── [runId]/page.tsx             # Run results
    │   ├── explanations/                    # F8
    │   │   └── page.tsx                     # Agent explanations with citations
    │   ├── approvals/                       # F9
    │   │   └── page.tsx                     # Human-in-the-loop approval queue
    │   ├── audit/                           # F9
    │   │   └── page.tsx                     # Versioned audit trail
    │   └── benchmarks/                      # F10
    │       └── page.tsx                     # Baselines vs full system, ablations
    │
    ├── components/
    │   ├── ui/                              # Buttons, cards, badges, tables, modals
    │   ├── layout/                          # Sidebar, Navbar, PageHeader
    │   ├── charts/                          # Recharts wrappers
    │   │   ├── UncertaintyBandChart.tsx
    │   │   ├── ScheduleGantt.tsx
    │   │   ├── MetricBarChart.tsx
    │   │   └── CalibrationPlot.tsx
    │   ├── evidence/
    │   │   ├── ProvenanceTimeline.tsx
    │   │   ├── ConflictCard.tsx
    │   │   └── EvidenceGraph.tsx
    │   ├── validity/
    │   │   ├── ValidityBadge.tsx            # verified / stale / invalidated / uncertain
    │   │   └── DependencyGraphView.tsx
    │   ├── planning/
    │   │   └── ScheduleDiffView.tsx
    │   └── approvals/
    │       └── ApprovalPanel.tsx
    │
    ├── lib/
    │   ├── api/                             # Typed REST/Fetch clients
    │   │   ├── client.ts                    # Base fetch wrapper (errors, auth)
    │   │   ├── ingestion.ts
    │   │   ├── evidence.ts
    │   │   ├── validity.ts
    │   │   ├── forecasts.ts
    │   │   ├── planning.ts
    │   │   ├── stress.ts
    │   │   ├── agents.ts
    │   │   ├── verification.ts
    │   │   └── benchmarks.ts
    │   ├── utils.ts
    │   └── constants.ts
    │
    ├── hooks/
    │   ├── useFetch.ts
    │   ├── usePolling.ts                    # Poll agent/run status
    │   └── useApproval.ts
    │
    ├── types/                               # TS types mirroring backend Pydantic schemas
    │   ├── evidence.ts
    │   ├── validity.ts
    │   ├── forecast.ts
    │   ├── schedule.ts
    │   ├── stress.ts
    │   ├── audit.ts
    │   └── index.ts
    │
    └── styles/
        └── theme.ts
```

---

## 3. Backend (Python + FastAPI + Pydantic + PostgreSQL)

Contains the API, domain services for each feature, agent orchestration, and independent verification.

```
backend/
├── pyproject.toml / requirements.txt
├── Dockerfile
├── alembic.ini                              # DB migrations config
├── .env.example
│
├── app/
│   ├── __init__.py
│   ├── main.py                              # FastAPI app entrypoint, router registration
│   │
│   ├── core/
│   │   ├── config.py                        # Pydantic Settings (env vars)
│   │   ├── logging.py
│   │   ├── security.py                      # Auth / API keys (if needed)
│   │   ├── exceptions.py
│   │   └── deps.py                          # FastAPI dependencies (DB session, etc.)
│   │
│   ├── db/
│   │   ├── session.py                       # SQLAlchemy engine/session
│   │   ├── base.py
│   │   ├── models/                          # ORM models
│   │   │   ├── record.py                    # Normalised records (F1)
│   │   │   ├── claim.py                     # Claims + provenance (F2)
│   │   │   ├── decision.py                  # Decisions + assumptions + versions (F3)
│   │   │   ├── forecast.py                  # (F4)
│   │   │   ├── schedule.py                  # (F5/F6)
│   │   │   ├── experiment.py                # Stress runs (F7)
│   │   │   ├── agent_run.py                 # Agent checkpoints (F8)
│   │   │   ├── approval.py                  # Human approvals (F9)
│   │   │   └── audit_log.py                 # Versioned audit trail (F9)
│   │   └── migrations/                      # Alembic versions
│   │
│   ├── schemas/                             # Pydantic request/response models
│   │   ├── ingestion.py
│   │   ├── evidence.py
│   │   ├── validity.py
│   │   ├── forecast.py
│   │   ├── planning.py
│   │   ├── stress.py
│   │   ├── agents.py
│   │   ├── verification.py
│   │   ├── audit.py
│   │   └── benchmarks.py
│   │
│   ├── api/
│   │   ├── router.py                        # Aggregates v1 routers
│   │   └── v1/
│   │       ├── health.py
│   │       ├── ingestion.py                 # F1
│   │       ├── evidence.py                  # F2
│   │       ├── validity.py                  # F3
│   │       ├── forecasts.py                 # F4
│   │       ├── planning.py                  # F5
│   │       ├── replanning.py                # F6
│   │       ├── stress.py                    # F7
│   │       ├── agents.py                    # F8 (submit request, get status/explanation)
│   │       ├── verification.py              # F9
│   │       ├── approvals.py                 # F9
│   │       ├── audit.py                     # F9
│   │       └── benchmarks.py                # F10
│   │
│   ├── services/                            # Business logic (one package per feature)
│   │   ├── ingestion/                       # F1
│   │   │   ├── validator.py                 # Schema validation
│   │   │   ├── normaliser.py                # Units, timestamps, formats
│   │   │   ├── deduplicator.py
│   │   │   └── entity_matcher.py            # Calls Ditto model from ml/
│   │   ├── evidence/                        # F2 · USP 1
│   │   │   ├── contradiction_detector.py
│   │   │   ├── staleness_checker.py
│   │   │   ├── provenance_tracer.py
│   │   │   ├── evidence_graph.py            # NetworkX graph builder
│   │   │   ├── uncertainty.py               # PyMC posteriors
│   │   │   └── autopsy.py                   # Builds the "Contradiction Autopsy" report
│   │   ├── validity/                        # F3 · USP 2
│   │   │   ├── dependency_graph.py          # NetworkX DAG of inputs → decisions
│   │   │   ├── assumption_tracker.py
│   │   │   ├── change_detector.py           # BOCPD wrapper
│   │   │   ├── reverifier.py                # Incremental re-verification
│   │   │   └── status.py                    # verified / stale / invalidated / uncertain
│   │   ├── forecasting/                     # F4
│   │   │   ├── features.py
│   │   │   ├── predictor.py                 # Loads DS-DGP / GP models
│   │   │   └── calibration.py
│   │   ├── planning/                        # F5 (thin layer over optimisation/)
│   │   │   ├── problem_builder.py
│   │   │   ├── solver_service.py
│   │   │   └── comparator.py                # Alternative schedule comparison
│   │   ├── replanning/                      # F6
│   │   │   ├── diff_inputs.py
│   │   │   ├── impact_analysis.py
│   │   │   ├── incremental_recompute.py
│   │   │   └── schedule_diff.py
│   │   ├── stress/                          # F7 (API-side orchestration)
│   │   │   └── run_manager.py
│   │   ├── explanation/                     # F8
│   │   │   └── explainer.py
│   │   ├── verification/                    # F9
│   │   │   ├── constraint_checker.py        # Independent deterministic validators
│   │   │   ├── consistency_checker.py
│   │   │   ├── uncertainty_flagger.py
│   │   │   └── approval_router.py
│   │   ├── audit/                           # F9
│   │   │   └── audit_service.py
│   │   └── benchmarking/                    # F10 (API-side access to results)
│   │       └── results_service.py
│   │
│   ├── agents/                              # F8 · LangGraph
│   │   ├── graph.py                         # Main StateGraph definition
│   │   ├── state.py                         # Typed state (Pydantic)
│   │   ├── routing.py                       # Conditional routing logic
│   │   ├── checkpointing.py                 # Postgres checkpointer
│   │   ├── retry.py                         # Bounded retry policy
│   │   ├── human_approval.py                # Interrupt / resume nodes
│   │   ├── nodes/
│   │   │   ├── evidence_agent.py
│   │   │   ├── prediction_agent.py
│   │   │   ├── change_analysis_agent.py
│   │   │   ├── optimisation_node.py
│   │   │   ├── verification_node.py         # Calls F9 validators (cannot be overridden)
│   │   │   └── explanation_agent.py
│   │   └── prompts/
│   │       ├── evidence.md
│   │       ├── explanation.md
│   │       └── change_analysis.md
│   │
│   └── utils/
│       ├── time.py
│       ├── ids.py
│       └── graph_utils.py
│
└── tests/
    ├── conftest.py                          # Fixtures: test DB, sample data
    ├── unit/
    │   ├── test_validator.py
    │   ├── test_deduplicator.py
    │   ├── test_contradiction_detector.py
    │   ├── test_dependency_graph.py
    │   ├── test_reverifier.py
    │   ├── test_constraint_checker.py
    │   └── test_schedule_diff.py
    ├── integration/
    │   ├── test_ingestion_flow.py
    │   ├── test_agent_workflow.py
    │   └── test_approval_flow.py
    └── api/
        ├── test_health.py
        ├── test_evidence_api.py
        └── test_planning_api.py
```

---

## 4. Streaming (Apache Kafka + Python consumers) — F1

```
streaming/
├── Dockerfile
├── requirements.txt
├── config/
│   ├── topics.yaml                          # Topic names, partitions, retention
│   └── schemas/                             # JSON/Avro schemas for each source
│       ├── resource.json
│       ├── crew.json
│       ├── availability.json
│       ├── weather.json
│       └── constraint.json
├── producers/
│   ├── base_producer.py
│   ├── synthetic_producer.py                # Replays synthetic data into Kafka
│   └── run_producer.py
├── consumers/
│   ├── base_consumer.py
│   ├── ingestion_consumer.py                # Validate → normalise → dedupe → store
│   ├── dead_letter_consumer.py              # Handles invalid/conflicting records
│   └── run_consumer.py
├── utils/
│   ├── kafka_client.py
│   └── serialization.py
└── tests/
    ├── test_producer.py
    └── test_consumer.py
```

---

## 5. ML Models (PyTorch, GPyTorch, PyMC) — F1, F2, F3, F4

```
ml/
├── requirements.txt
├── entity_matching/                         # F1 — Ditto Transformer
│   ├── ditto_model.py
│   ├── train.py
│   ├── infer.py
│   └── configs/ditto.yaml
├── temporal_graph/                          # F2 — TGN / StrGNN benchmark candidates
│   ├── tgn/
│   │   ├── model.py
│   │   └── train.py
│   ├── strgnn/
│   │   ├── model.py
│   │   └── train.py
│   ├── dataset.py                           # Builds temporal graph from Postgres
│   ├── evaluate.py                          # Head-to-head comparison
│   └── configs/
├── bayesian/                                # F2 — PyMC
│   ├── source_reliability.py                # Hierarchical source-trust model
│   ├── claim_posterior.py
│   └── diagnostics.py                       # Convergence checks
├── change_point/                            # F3 — BOCPD
│   ├── bocpd.py
│   └── hazard.py
├── forecasting/                             # F4
│   ├── ds_dgp/
│   │   ├── model.py                         # Doubly Stochastic Deep GP (GPyTorch)
│   │   └── train.py
│   ├── baselines/
│   │   ├── sparse_gp.py
│   │   ├── lstm.py
│   │   └── arima.py
│   ├── calibration.py                       # ECE, coverage, NLL
│   └── configs/
├── artifacts/                               # Saved weights (git-ignored; tracked via MLflow)
│   └── .gitkeep
└── notebooks/
    ├── 01_entity_matching_exploration.ipynb
    ├── 02_temporal_graph_benchmark.ipynb
    └── 03_forecast_uncertainty.ipynb
```

---

## 6. Optimisation (OR-Tools CP-SAT + ALNS) — F5, F6

```
optimisation/
├── requirements.txt
├── models/
│   ├── problem.py                           # Dataclasses: resources, tasks, windows
│   └── solution.py
├── cpsat/
│   ├── model_builder.py                     # Variables + constraints
│   ├── constraints/
│   │   ├── resource_capacity.py
│   │   ├── time_windows.py
│   │   ├── precedence.py
│   │   └── policy.py
│   ├── objectives.py                        # Makespan, cost, lateness, robustness
│   └── solver.py
├── alns/
│   ├── destroy_operators.py
│   ├── repair_operators.py
│   ├── hybrid.py                            # CP-SAT warm-start + ALNS improvement
│   └── runner.py
├── incremental/                             # F6
│   ├── warm_start.py                        # Reuse previous solution
│   └── partial_resolve.py                   # Re-solve only affected subproblem
├── benchmarks/                              # Synthetic problem instances
│   └── instances/
└── tests/
    ├── test_cpsat.py
    ├── test_alns.py
    └── test_feasibility.py
```

---

## 7. Simulation & Fault Injection (SimPy + Hypothesis) — F7 · USP 3

```
simulation/
├── requirements.txt
├── twin/
│   ├── environment.py                       # SimPy environment
│   ├── entities.py                          # Resources, crews, tasks
│   └── clock.py
├── faults/
│   ├── missing_data.py
│   ├── stale_data.py
│   ├── conflicting_data.py
│   ├── constraint_change.py
│   └── injector.py                          # Seeded, reproducible injection
├── scenarios/
│   ├── library/                             # YAML scenario definitions
│   │   ├── baseline_clean.yaml
│   │   ├── heavy_staleness.yaml
│   │   ├── source_conflict.yaml
│   │   └── cascading_changes.yaml
│   ├── generator.py                         # Hypothesis-driven scenario generation
│   └── loader.py
├── runner/
│   ├── run_scenario.py
│   ├── metrics.py                           # Detection rate, false alarms, recovery time
│   └── mlflow_logger.py
├── properties/                              # Hypothesis property-based tests
│   ├── test_invariants.py
│   └── test_no_invalid_accept.py            # Invalid results never reach approval
└── tests/
    └── test_reproducibility.py              # Same seed → identical run
```

---

## 8. Evaluation & Benchmarking (MLflow, pandas, SciPy) — F10

```
evaluation/
├── requirements.txt
├── baselines/
│   ├── naive_pipeline.py                    # No evidence tracking, no revalidation
│   ├── rule_based_only.py
│   └── full_recompute.py                    # Baseline for incremental re-verification
├── ablations/
│   ├── no_evidence_intelligence.py          # Disable F2
│   ├── no_validity_tracking.py              # Disable F3
│   ├── no_uncertainty.py                    # Disable F4 uncertainty
│   ├── no_alns.py                           # CP-SAT only
│   └── no_independent_verification.py       # Disable F9
├── metrics/
│   ├── latency.py
│   ├── feasibility.py
│   ├── error_detection.py                   # Precision / recall of data-error detection
│   ├── false_alarms.py
│   ├── recovery.py
│   └── calibration.py                       # ECE, coverage
├── stats/
│   ├── significance.py                      # SciPy tests (Wilcoxon, t-test, bootstrap CI)
│   └── effect_size.py
├── experiments/
│   ├── exp_evidence_detection.py
│   ├── exp_incremental_vs_full.py
│   ├── exp_forecast_calibration.py
│   ├── exp_hybrid_solver.py
│   └── exp_stress_end_to_end.py
├── reports/
│   ├── generate_report.py                   # Tables + figures from MLflow runs
│   └── output/                              # Generated (git-ignored)
├── mlflow/
│   └── mlflow_config.py
└── tests/
    └── test_metrics.py
```

---

## 9. Data (Synthetic Only)

```
data/
├── README.md                                # States: all data is synthetic, non-operational
├── generators/
│   ├── generate_resources.py
│   ├── generate_crew.py
│   ├── generate_availability.py
│   ├── generate_weather.py
│   ├── generate_constraints.py
│   └── generate_all.py                      # Seeded master generator
├── schemas/
│   └── data_dictionary.md
├── samples/                                 # Small committed samples for tests/demo
│   ├── resources_sample.csv
│   ├── crew_sample.csv
│   └── constraints_sample.json
├── raw/                                     # Generated (git-ignored)
└── processed/                               # Generated (git-ignored)
```

---

## 10. Infrastructure & Deployment

```
infra/
├── docker/
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   ├── streaming.Dockerfile
│   ├── mlflow.Dockerfile
│   └── simulation.Dockerfile
├── postgres/
│   ├── init.sql                             # Extensions, schemas, roles
│   └── seed.sql
├── kafka/
│   ├── create_topics.sh
│   └── server.properties                    # If self-managed
├── mlflow/
│   └── entrypoint.sh
├── nginx/                                   # Optional reverse proxy
│   └── nginx.conf
└── env/
    ├── dev.env.example
    └── prod.env.example
```

---

## 11. Documentation

```
docs/
├── architecture/
│   ├── system_overview.md
│   ├── workflow_steps.md                    # The 12-step system workflow
│   ├── agentic_workflow.md                  # LangGraph architecture
│   └── diagrams/
│       ├── system.drawio
│       ├── agentic_flow.png
│       └── er_diagram.png
├── features/
│   ├── F01_ingestion.md
│   ├── F02_evidence_intelligence.md
│   ├── F03_validity_envelope.md
│   ├── F04_prediction.md
│   ├── F05_planning.md
│   ├── F06_replanning.md
│   ├── F07_stress_lab.md
│   ├── F08_agentic_explanation.md
│   ├── F09_verification_audit.md
│   └── F10_benchmarking.md
├── usps/
│   ├── USP1_contradiction_autopsy.md
│   ├── USP2_decision_validity_envelope.md
│   └── USP3_adversarial_digital_twin.md
├── api/
│   └── openapi.json                         # Exported from FastAPI
├── research/
│   ├── model_selection.md                   # TGN vs StrGNN, DS-DGP rationale
│   └── evaluation_protocol.md
├── setup/
│   ├── local_setup.md
│   └── troubleshooting.md
└── CONTRIBUTING.md
```

---

## 12. Cross-Module Tests

```
tests/
├── conftest.py
├── e2e/
│   ├── test_full_pipeline.py                # Kafka → DB → agents → verification → dashboard API
│   ├── test_replan_on_change.py
│   └── test_human_approval_gate.py
├── contract/
│   └── test_frontend_backend_schemas.py     # TS types ↔ Pydantic schema parity
└── performance/
    └── test_latency_budget.py
```

---

## 13. Feature → Folder Quick Map

| Feature | Backend | Other Modules | Frontend Route |
|---|---|---|---|
| F1 Ingestion | `services/ingestion`, `api/v1/ingestion.py` | `streaming/`, `ml/entity_matching` | `/ingestion` |
| F2 Evidence (USP 1) | `services/evidence` | `ml/temporal_graph`, `ml/bayesian` | `/evidence` |
| F3 Validity (USP 2) | `services/validity` | `ml/change_point` | `/validity` |
| F4 Prediction | `services/forecasting` | `ml/forecasting` | `/forecasts` |
| F5 Planning | `services/planning` | `optimisation/cpsat`, `optimisation/alns` | `/planning` |
| F6 Replanning | `services/replanning` | `optimisation/incremental` | `/planning/compare` |
| F7 Stress Lab (USP 3) | `services/stress` | `simulation/` | `/stress-lab` |
| F8 Agentic AI | `agents/`, `services/explanation` | — | `/explanations` |
| F9 Verification & Audit | `services/verification`, `services/audit` | — | `/approvals`, `/audit` |
| F10 Benchmarking | `services/benchmarking` | `evaluation/` | `/benchmarks` |

---

## 14. Suggested Build Order

1. **Root + infra**: `docker-compose.yml`, Postgres, Kafka, `.env.example`
2. **F1**: `streaming/` + `backend/services/ingestion` + synthetic `data/generators`
3. **F9 core (validators + audit)**: build the deterministic checks early; everything else depends on them
4. **F5**: `optimisation/cpsat` → then `alns`
5. **F2, F3**: evidence graph, dependency graph, BOCPD
6. **F4**: baselines first, then DS-DGP
7. **F6**: incremental replanning
8. **F8**: LangGraph agents wired to existing services
9. **F7**: simulation + fault injection
10. **F10**: baselines, ablations, MLflow reports
11. **Frontend**: build pages alongside each backend feature
