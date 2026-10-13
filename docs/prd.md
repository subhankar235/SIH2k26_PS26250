# Air Power — Product Requirements Document (PRD)

| Field | Value |
|---|---|
| Product | Air Power |
| Document | Product Requirements Document |
| Version | 1.0 (Draft) |
| Status | For review |
| Scope | Synthetic, non-operational resource scheduling, data reliability, decision support, and evaluation |
| Related docs | `AIR_POWER_FILE_STRUCTURE.md` |

---

## Table of Contents

1. Overview
2. Problem Statement
3. Goals, Non-Goals, and Success Criteria
4. Scope and Constraints
5. Target Users and Personas
6. Core Differentiators (USPs)
7. System Architecture
8. Functional Requirements (F1–F10)
9. Agentic Workflow Requirements
10. Data Requirements
11. API Requirements
12. User Interface Requirements
13. Non-Functional Requirements
14. Tech Stack
15. Evaluation and Benchmarking Plan
16. Metrics and KPIs
17. Testing Strategy
18. Security, Safety, and Ethics
19. Deployment and Environments
20. Milestones and Delivery Plan
21. Risks and Mitigations
22. Assumptions, Dependencies, and Open Questions
23. Out of Scope
24. Glossary
25. Traceability Matrix

---

## 1. Overview

**Air Power** is a decision-support platform for resource scheduling that treats *data reliability* and *decision validity* as first-class concerns. It ingests multi-source synthetic records (resources, crew, availability, weather, constraints), detects and explains data conflicts, forecasts demand or availability with uncertainty, generates feasible schedules, and continuously tracks whether previous recommendations remain valid as inputs change.

The system is evaluated through a controlled, adversarial digital twin that injects missing, stale, and conflicting data, so reliability is *demonstrated through experiments* rather than claimed through a clean demo.

All data is **synthetic and non-operational**. The project is a research/engineering system for studying reliable decision support.

### 1.1 Product Vision

A scheduling decision-support system that does not just produce a plan, but can show **why the data behind it can be trusted, whether the plan is still valid, and how it behaves when information goes wrong**.

### 1.2 One-Line Pitch

*An evidence-aware, change-aware, stress-tested scheduling system where every recommendation is traceable, verifiable, and auditable.*

---

## 2. Problem Statement

Scheduling and resource-allocation systems commonly fail in three ways:

1. **Unreliable inputs.** Data from multiple sources is conflicting, outdated, duplicated, or incomplete. Typical systems flag bad data without explaining *why* it is bad or where it came from.
2. **Silent staleness of decisions.** A recommendation that was correct yesterday may be invalid today because an input or assumption changed. Systems either ignore this or blindly recompute everything.
3. **Untested under failure.** Systems look successful under clean data and fail when information degrades or constraints change. Reliability claims are rarely backed by controlled experiments.

Additionally, AI-assisted components (agents, learned models) can produce unsupported outputs. There must be an independent, deterministic layer that prevents invalid results from being accepted.

---

## 3. Goals, Non-Goals, and Success Criteria

### 3.1 Goals

| ID | Goal |
|---|---|
| G1 | Ingest, validate, normalise, and deduplicate multi-source streaming data reliably. |
| G2 | Detect stale, missing, duplicate, and conflicting claims and explain their provenance and history (USP 1). |
| G3 | Track the validity of every recommendation and re-verify only what is affected by a change (USP 2). |
| G4 | Forecast resource demand/availability with calibrated uncertainty. |
| G5 | Generate feasible schedules under resource, time, and policy constraints and compare alternatives. |
| G6 | Replan incrementally when inputs or constraints change and explain the delta. |
| G7 | Stress-test the whole system with reproducible fault injection (USP 3). |
| G8 | Coordinate analysis through bounded, typed agent workflows that cannot override deterministic validators. |
| G9 | Independently verify, audit, and route uncertain or invalid results to a human. |
| G10 | Prove, with baselines, ablations, and statistics, whether the system improves reliability or performance. |

### 3.2 Non-Goals

- Operating on, or integrating with, real operational or classified data or systems.
- Real-time safety-critical control.
- Replacing human decision-makers (human approval is mandatory for verified results).
- Building a general-purpose scheduling product for production use.
- Training large foundation models.

### 3.3 Success Criteria

| ID | Criterion | Target (to be confirmed in baseline run) |
|---|---|---|
| SC1 | Data-error detection recall on injected faults | Significantly higher than naive baseline (p < 0.05) |
| SC2 | False-alarm rate on clean data | At or below a defined threshold (initial target ≤ 5%) |
| SC3 | Incremental re-verification latency vs full recompute | Meaningfully lower, with equivalent correctness |
| SC4 | Schedule feasibility rate | 100% of accepted schedules pass independent verification |
| SC5 | Forecast uncertainty calibration | Coverage within ±5 percentage points of nominal on synthetic test sets |
| SC6 | Invalid results accepted by the system | 0 (enforced by independent verifier + property tests) |
| SC7 | Reproducibility | Same seed and config produce identical experiment results |
| SC8 | Traceability | Every displayed recommendation links to evidence, versions, and audit entries |

---

## 4. Scope and Constraints

### 4.1 In Scope

- Synthetic data generation, streaming ingestion, storage, and normalisation.
- Evidence intelligence, validity tracking, forecasting, planning, replanning.
- Digital twin with fault injection.
- Agentic orchestration and explanations.
- Independent verification, audit, and human approval.
- Benchmarking, ablations, and statistical evaluation.
- Web dashboard for all of the above.

### 4.2 Constraints

- **Synthetic-only data.** No real operational data is used or required.
- **Deterministic validators are authoritative.** Agents and learned models are advisory.
- **Reproducibility.** All stochastic components accept seeds; experiments are logged.
- **Local-first.** The full stack must run via Docker Compose on a developer machine.
- **Model candidates are benchmarked, not assumed.** TGN/StrGNN and DS-DGP are research candidates; simpler baselines must be compared before adoption.

---

## 5. Target Users and Personas

| Persona | Description | Primary Needs |
|---|---|---|
| **Scheduler / Planner** | Builds and reviews schedules. | Feasible plans, alternatives, clear change impact, knowing when a plan is stale. |
| **Data Quality Analyst** | Investigates conflicting or suspicious records. | Contradiction autopsy, provenance timeline, uncertainty, missing-data visibility. |
| **Reviewer / Approver** | Human-in-the-loop for final acceptance. | Verified results, evidence, explanation, uncertainty flags, approve/reject with audit. |
| **Researcher / Evaluator** | Assesses whether the system works. | Reproducible experiments, baselines, ablations, statistical results. |
| **Developer / Maintainer** | Extends and operates the system. | Clear module boundaries, tests, logs, typed schemas. |

### 5.1 Key User Stories

| ID | As a… | I want to… | So that… |
|---|---|---|---|
| US1 | Data analyst | see why two records disagree and how each claim changed over time | I can resolve the conflict with evidence. |
| US2 | Planner | see whether an earlier recommendation is still valid after a data change | I don't act on stale decisions. |
| US3 | Planner | get a forecast with uncertainty bands | I know when to trust the prediction. |
| US4 | Planner | get feasible schedules and compare alternatives | I can pick a trade-off between objectives. |
| US5 | Planner | see what changed between old and updated schedules | I can understand replanning impact. |
| US6 | Researcher | run reproducible fault-injection scenarios | I can measure detection, false alarms, and recovery. |
| US7 | Reviewer | approve or reject only verified results with evidence | Invalid or uncertain results never pass silently. |
| US8 | Researcher | compare the full system with baselines and ablations | I can prove which components matter. |
| US9 | Auditor | inspect a versioned history of decisions and changes | I can reconstruct why a decision was made. |

---

## 6. Core Differentiators (USPs)

### USP 1 — Temporal Evidence Intelligence & Contradiction Autopsy (F2)

- **Problem:** Data across sources is conflicting, outdated, duplicated, or incomplete.
- **Capability:** Detects contradictions, stale records, missing data, duplicates; traces origin and change history of each claim; shows supporting evidence, uncertainty, and what is missing.
- **Unique value:** Explains the *history and evidence behind* a conflict instead of only flagging it.
- **Technology:** Kafka, PostgreSQL, NetworkX, PyMC, PyTorch, TGN/StrGNN candidates.

### USP 2 — Decision Validity Envelope & Incremental Re-Verification (F3)

- **Problem:** Recommendations become unreliable when inputs or assumptions change.
- **Capability:** Tracks input versions, assumptions, and dependencies per recommendation; detects invalidating changes; rechecks only affected dependencies; labels results **verified / stale / invalidated / uncertain**.
- **Unique value:** Tracks not only what the system recommends but whether it *remains valid*.
- **Technology:** NetworkX, BOCPD, PostgreSQL, Python, deterministic validation rules.

### USP 3 — Adversarial Digital Twin & Decision Stress Laboratory (F7)

- **Problem:** Systems look successful on clean data but fail under unreliable information.
- **Capability:** Generates reproducible synthetic scenarios; injects missing, stale, conflicting records and changing constraints; tests against baselines; measures detection, false alarms, feasibility, recovery, reliability.
- **Unique value:** Reliability shown through controlled experiments rather than a successful demo.
- **Technology:** SimPy, Hypothesis, NumPy, SciPy, MLflow.

---

## 7. System Architecture

### 7.1 High-Level Components

| Layer | Components |
|---|---|
| Presentation | Next.js + TypeScript dashboard (Tailwind, Recharts) |
| API | FastAPI (REST), Pydantic schemas |
| Orchestration | LangGraph agent workflows with checkpointing |
| Domain services | Ingestion, evidence, validity, forecasting, planning, replanning, verification, audit, benchmarking |
| Data / streaming | Apache Kafka, Python consumers, PostgreSQL |
| ML | Ditto (entity matching), TGN/StrGNN, PyMC, BOCPD, DS-DGP/GPyTorch |
| Optimisation | OR-Tools CP-SAT, ALNS |
| Simulation / testing | SimPy, Hypothesis, Pytest |
| Experiment tracking | MLflow |
| Infrastructure | Docker, Docker Compose, Git/GitHub |

### 7.2 System Workflow (12 Steps)

| Step | Stage | Feature | Description |
|---|---|---|---|
| 1 | Data sources | — | Collect synthetic resource, crew, availability, weather, and constraint records. |
| 2 | Kafka streaming | F1 | Kafka receives and streams events to Python consumers. |
| 3 | Data validation | F1 | FastAPI, Pydantic, Python validate, normalise, timestamp, deduplicate; PostgreSQL stores. |
| 4 | Evidence intelligence | F2 · USP 1 | NetworkX, PyMC, benchmarked temporal graph models find conflicting/stale/missing/duplicate records and trace provenance. |
| 5 | Decision validity tracking | F3 · USP 2 | Dependency graph + BOCPD flag changed assumptions; deterministic checks decide re-verification. |
| 6 | Predictive intelligence | F4 | PyTorch and benchmarked DS-DGP estimate demand/availability with uncertainty. |
| 7 | Constraint-based planning | F5 | CP-SAT generates feasible schedules; ALNS searches for improvements. |
| 8 | Change impact & replanning | F6 | Detect changed inputs, identify affected dependencies, re-evaluate schedule. |
| 9 | Digital twin stress testing | F7 · USP 3 | SimPy and Hypothesis generate reproducible fault scenarios. |
| 10 | Agentic coordination | F8 | LangGraph coordinates evidence analysis, verification, experiment analysis, explanation. |
| 11 | Independent verification | F9 | Pydantic, Python rules, Pytest check constraints; uncertain/invalid results go to human review. |
| 12 | Explainability & benchmarking | F10 | Dashboard shows results, provenance, uncertainty, audit history, baselines; MLflow tracks experiments. |

### 7.3 Request Lifecycle (Agentic Architecture)

1. **User / Dashboard** submits a request.
2. **FastAPI backend** receives and validates input.
3. **LangGraph orchestrator** controls agent execution, state, and routing.
4. **Specialised agents** run: Evidence Agent, Prediction Agent, Change Analysis Agent.
5. **Optimisation engine** (CP-SAT) generates feasible schedules.
6. **Independent verification** applies deterministic rules for constraints and consistency.
7. **Verification result:**
   - `INVALID` / `UNCERTAIN` → return for re-analysis (bounded retries).
   - `VERIFIED` → Human Approval.
8. **Dashboard** displays results, evidence, explanations.
9. **Audit log and metrics** store decisions, validation results, performance data.

### 7.4 Architectural Principles

- **Deterministic authority:** validators outrank agents and models.
- **Evidence first:** every output links back to source records and versions.
- **Incremental by default:** recompute only what a change affects.
- **Uncertainty is a first-class output,** not an afterthought.
- **Reproducibility:** seeds, versions, and configs recorded for every run.
- **Bounded autonomy:** agent retries and loops are capped; humans approve.

---

## 8. Functional Requirements

Priority key: **P0** = must have, **P1** = should have, **P2** = nice to have.

### F1. Multi-Source Data Ingestion & Normalisation

**Purpose:** Reliable ingestion of heterogeneous synthetic data.
**Stack:** Apache Kafka, Python, FastAPI, Pydantic, PostgreSQL. Ditto Transformer for ambiguous entity matching.

| ID | Requirement | Priority |
|---|---|---|
| F1.1 | Kafka topics SHALL exist per source type (resource, crew, availability, weather, constraint). | P0 |
| F1.2 | Consumers SHALL validate each message against a Pydantic schema. | P0 |
| F1.3 | Consumers SHALL normalise units, formats, identifiers, and timestamps (event time and ingest time both stored). | P0 |
| F1.4 | The system SHALL deduplicate records using deterministic keys first, then entity matching for ambiguous cases. | P0 |
| F1.5 | Ditto-based entity matching SHALL return a match probability; low-confidence matches SHALL be flagged, not auto-merged. | P1 |
| F1.6 | Invalid or conflicting records SHALL NOT be dropped; they SHALL be stored and flagged for evidence analysis (dead-letter handling). | P0 |
| F1.7 | Ingestion SHALL be idempotent (replaying a message does not create duplicates). | P0 |
| F1.8 | Each stored record SHALL retain source, version, and raw payload reference. | P0 |
| F1.9 | The dashboard SHALL show stream status, validation error counts, and flagged records. | P1 |

**Acceptance criteria:** Replay of a 10k-record synthetic stream yields no duplicate rows, all invalid records appear in the flagged set with reasons, and every row has source + timestamps.

---

### F2. Temporal Evidence Intelligence & Contradiction Autopsy — USP 1

**Purpose:** Discover why records disagree and show their evidence history.
**Stack:** PostgreSQL, NetworkX, PyMC, PyTorch. Candidates: TGN, StrGNN.

| ID | Requirement | Priority |
|---|---|---|
| F2.1 | The system SHALL detect four issue classes: **stale, missing, duplicate, conflicting** claims. | P0 |
| F2.2 | The system SHALL maintain an evidence graph linking claims, sources, entities, and time. | P0 |
| F2.3 | For any flagged record, the system SHALL produce a **Contradiction Autopsy**: the competing claims, their sources, timestamps, change history, and supporting evidence. | P0 |
| F2.4 | The autopsy SHALL list **what information is missing** to resolve the conflict. | P0 |
| F2.5 | The system SHALL estimate per-claim and per-source reliability with uncertainty (PyMC Bayesian model). | P1 |
| F2.6 | TGN and StrGNN SHALL be benchmarked against simpler baselines (rule-based, statistical); adoption is conditional on measured benefit. | P1 |
| F2.7 | Staleness SHALL be defined per data type via configurable freshness thresholds. | P0 |
| F2.8 | Provenance SHALL be queryable: origin source, transformations, and version chain. | P0 |
| F2.9 | The dashboard SHALL render a provenance timeline and conflict cards. | P1 |

**Acceptance criteria:** For each injected fault in a labelled synthetic set, the system reports the correct class, and the autopsy lists the originating sources and at least the true missing-information items.

---

### F3. Decision Validity Envelope & Incremental Re-Verification — USP 2

**Purpose:** Determine whether a previous recommendation remains valid after changes.
**Stack:** Python, NetworkX, PostgreSQL, Pytest. Technique: BOCPD + dependency graph.

| ID | Requirement | Priority |
|---|---|---|
| F3.1 | Every recommendation SHALL record its **input versions, assumptions, and dependencies** (the "validity envelope"). | P0 |
| F3.2 | The system SHALL maintain a dependency graph from inputs and assumptions to decisions. | P0 |
| F3.3 | BOCPD SHALL monitor relevant time series for change points that may violate assumptions. | P1 |
| F3.4 | On any input change, the system SHALL identify affected decisions via graph traversal. | P0 |
| F3.5 | The system SHALL re-verify **only affected** dependencies and not the entire workflow. | P0 |
| F3.6 | Each decision SHALL carry exactly one status: **verified, stale, invalidated, uncertain**. | P0 |
| F3.7 | Status transitions SHALL be recorded in the audit trail with the triggering change. | P0 |
| F3.8 | Incremental re-verification results SHALL match a full recomputation (correctness check). | P0 |
| F3.9 | The dashboard SHALL show validity status and a dependency graph view per decision. | P1 |

**Status definitions**

| Status | Meaning |
|---|---|
| Verified | All inputs and assumptions unchanged or re-checked and satisfied. |
| Stale | Inputs changed or aged but impact not yet determined. |
| Invalidated | A change violates a constraint or assumption; decision no longer holds. |
| Uncertain | Evidence insufficient or conflicting to decide validity. |

**Acceptance criteria:** In a test suite of change events, incremental re-verification yields the same statuses as full recompute while touching strictly fewer nodes when changes are local.

---

### F4. Predictive Intelligence & Uncertainty Estimation

**Purpose:** Forecast resource demand/availability with quantified uncertainty.
**Stack:** PyTorch, GPyTorch, pandas, NumPy. Candidate: DS-DGP.

| ID | Requirement | Priority |
|---|---|---|
| F4.1 | The system SHALL produce forecasts with predictive intervals (mean + uncertainty). | P0 |
| F4.2 | DS-DGP SHALL be benchmarked against baselines (e.g., sparse GP, LSTM, ARIMA). | P1 |
| F4.3 | Forecast uncertainty SHALL be exposed to downstream components so they can distinguish confident from unreliable predictions. | P0 |
| F4.4 | Calibration SHALL be measured (coverage, ECE, NLL). | P0 |
| F4.5 | Forecasts SHALL be versioned and linked to input data versions (for F3). | P0 |
| F4.6 | The system SHALL flag forecasts whose uncertainty exceeds a configurable threshold. | P1 |
| F4.7 | The dashboard SHALL display forecasts with uncertainty bands. | P1 |

**Acceptance criteria:** On held-out synthetic data, empirical coverage of nominal 90% intervals is within ±5 points; the model is compared with at least two baselines.

---

### F5. Constraint-Based Planning & Optimisation

**Purpose:** Generate feasible schedules under resource, time, and policy constraints.
**Stack:** OR-Tools CP-SAT, Python `alns`. Technique: hybrid CP-SAT + ALNS.

| ID | Requirement | Priority |
|---|---|---|
| F5.1 | The system SHALL model resource capacity, time windows, precedence, and policy constraints. | P0 |
| F5.2 | CP-SAT SHALL produce feasible schedules or report infeasibility with reason. | P0 |
| F5.3 | ALNS SHALL attempt improvement from a CP-SAT solution within a time budget. | P1 |
| F5.4 | The system SHALL support multiple objectives (e.g., makespan, cost, lateness, robustness) and report trade-offs. | P1 |
| F5.5 | The system SHALL generate and compare alternative schedules. | P1 |
| F5.6 | Forecast uncertainty (F4) MAY be used as an input (e.g., buffers or robust constraints). | P2 |
| F5.7 | Solver runs SHALL be seeded/time-bounded and logged for reproducibility. | P0 |
| F5.8 | Every schedule SHALL be passed to independent verification (F9) before acceptance. | P0 |

**Acceptance criteria:** On a library of synthetic instances, 100% of returned schedules satisfy all declared constraints under the independent checker; hybrid CP-SAT+ALNS is compared with CP-SAT alone.

---

### F6. Dynamic Replanning & Change Impact Analysis

**Purpose:** Update schedules when inputs or constraints change.
**Stack:** Python, FastAPI, NetworkX, OR-Tools.

| ID | Requirement | Priority |
|---|---|---|
| F6.1 | The system SHALL diff input versions to identify exactly what changed. | P0 |
| F6.2 | It SHALL determine which schedule elements and decisions are affected (using F3 graph). | P0 |
| F6.3 | It SHALL recompute incrementally (warm start / partial re-solve) where possible. | P1 |
| F6.4 | It SHALL fall back to full re-solve when incremental recompute cannot guarantee feasibility. | P0 |
| F6.5 | It SHALL produce a **schedule diff** (added, removed, moved, unchanged assignments). | P0 |
| F6.6 | Updated schedules SHALL be independently verified. | P0 |
| F6.7 | The dashboard SHALL display old vs. updated schedules side by side. | P1 |

**Acceptance criteria:** After injected input changes, the updated schedule is feasible, the diff accurately reflects changes, and incremental runs are faster than full re-solve on local changes.

---

### F7. Adversarial Digital Twin & Decision Stress Laboratory — USP 3

**Purpose:** Test reliability under controlled failures.
**Stack:** SimPy, Hypothesis, NumPy, SciPy, MLflow.

| ID | Requirement | Priority |
|---|---|---|
| F7.1 | The twin SHALL simulate synthetic resources, crews, tasks, and event timelines (SimPy). | P0 |
| F7.2 | The injector SHALL support fault types: **missing, stale, conflicting data**, and **changing constraints**. | P0 |
| F7.3 | All scenarios SHALL be reproducible from a seed + scenario config. | P0 |
| F7.4 | Hypothesis SHALL generate scenario variations and property tests (e.g., "invalid results are never accepted"). | P1 |
| F7.5 | Each run SHALL measure: detection rate, false alarms, failure rate, feasibility, recovery time. | P0 |
| F7.6 | Runs SHALL compare the full system against baselines. | P0 |
| F7.7 | Runs and metrics SHALL be logged to MLflow. | P0 |
| F7.8 | The dashboard SHALL allow launching scenarios and viewing results. | P1 |

**Acceptance criteria:** Re-running a scenario with the same seed produces identical metrics; a scenario library covers each fault type and combinations.

---

### F8. Evidence-Backed Explanation & Agentic AI

**Purpose:** Coordinate analysis and produce traceable explanations.
**Stack:** LangGraph, Python, FastAPI, Pydantic.

| ID | Requirement | Priority |
|---|---|---|
| F8.1 | Workflows SHALL be implemented as a typed LangGraph state graph (Pydantic state). | P0 |
| F8.2 | Agents: **Evidence Agent**, **Prediction Agent**, **Change Analysis Agent**, plus optimisation, verification, and explanation nodes. | P0 |
| F8.3 | Routing SHALL be conditional on verification results (INVALID/UNCERTAIN → re-analysis; VERIFIED → approval). | P0 |
| F8.4 | Workflow state SHALL be checkpointed (resumable after failure or human pause). | P0 |
| F8.5 | Retries SHALL be bounded (max attempts configurable); exhausted retries escalate to a human. | P0 |
| F8.6 | Human-in-the-loop approval SHALL be an explicit graph interrupt. | P0 |
| F8.7 | **Agents SHALL NOT override deterministic validators.** | P0 |
| F8.8 | Every explanation SHALL cite concrete evidence (record IDs, versions, validator results); unsupported statements SHALL be rejected. | P0 |
| F8.9 | Agent inputs/outputs SHALL be schema-validated. | P0 |

**Acceptance criteria:** Property tests show no path exists in which a result failing F9 reaches approval; every explanation contains resolvable evidence references.

---

### F9. Independent Verification, Audit & Human Approval

**Purpose:** Prevent unsupported or invalid results from being accepted.
**Stack:** Pydantic, PostgreSQL, Pytest, FastAPI.

| ID | Requirement | Priority |
|---|---|---|
| F9.1 | A verifier independent of the solver and agents SHALL check all constraints (capacity, time windows, precedence, policy). | P0 |
| F9.2 | It SHALL check consistency between schedule, forecasts, and evidence versions. | P0 |
| F9.3 | It SHALL flag uncertainty (high forecast uncertainty, unresolved conflicts, uncertain validity status). | P0 |
| F9.4 | Outcomes SHALL be one of: verified, invalid, uncertain. | P0 |
| F9.5 | Results needing review SHALL be routed to a human approval queue. | P0 |
| F9.6 | Approvals/rejections SHALL record approver, time, rationale. | P0 |
| F9.7 | A **versioned, append-only audit trail** SHALL record evidence, inputs, decisions, validation results, status changes, and approvals. | P0 |
| F9.8 | The audit trail SHALL support reconstruction of any past decision. | P0 |
| F9.9 | The dashboard SHALL show the approval queue and audit history. | P1 |

**Acceptance criteria:** Intentionally corrupted schedules are always rejected by the verifier; audit entries cannot be modified or deleted via the API.

---

### F10. Benchmarking, Ablations & Performance Evaluation

**Purpose:** Prove whether the system improves reliability or performance.
**Stack:** MLflow, pandas, SciPy, Pytest.

| ID | Requirement | Priority |
|---|---|---|
| F10.1 | The suite SHALL compare the full system against simpler baselines (naive pipeline, rule-based only, full recompute). | P0 |
| F10.2 | The suite SHALL run **ablations** disabling each major component (F2, F3, F4 uncertainty, ALNS, F9). | P0 |
| F10.3 | Metrics SHALL include: latency, feasibility, data-error detection (precision/recall), false alarms, recovery, uncertainty calibration. | P0 |
| F10.4 | Results SHALL include statistical tests and confidence intervals (SciPy). | P0 |
| F10.5 | Experiments SHALL be reproducible and tracked in MLflow with seeds, configs, versions. | P0 |
| F10.6 | The system SHALL generate report tables and figures. | P1 |
| F10.7 | The dashboard SHALL show baseline and ablation comparisons. | P1 |

**Acceptance criteria:** A single command reproduces the full benchmark and report; results report effect sizes with confidence intervals.

---

## 9. Agentic Workflow Requirements

### 9.1 Agents

| Agent / Node | Responsibility |
|---|---|
| Evidence Agent | Checks data quality, contradictions, provenance (uses F2 services). |
| Prediction Agent | Estimates demand/availability with uncertainty (uses F4). |
| Change Analysis Agent | Identifies changed inputs and affected dependencies (uses F3/F6). |
| Optimisation node | Invokes CP-SAT (and ALNS) to generate schedules. |
| Verification node | Invokes F9 deterministic validators; authoritative. |
| Explanation agent | Produces evidence-cited explanations. |

### 9.2 Control Rules

- Maximum retry count per node and per workflow (configurable, default 3).
- Re-analysis loops must change inputs or parameters; identical retries are disallowed.
- Agent outputs are Pydantic-validated; schema failure counts as a retry.
- Verification result gates the path to human approval.
- All state transitions are checkpointed and logged.

### 9.3 State Machine (Summary)

```
START → Request validated → Evidence/Prediction/Change agents
      → Optimisation → Independent Verification
          ├─ INVALID / UNCERTAIN → Re-analysis (bounded) → … or escalate to human
          └─ VERIFIED → Human Approval → Dashboard → Audit log & metrics → END
```

---

## 10. Data Requirements

### 10.1 Data Domains (Synthetic)

| Domain | Examples |
|---|---|
| Resources | Identifier, type, capacity, status, location (abstract) |
| Crew | Identifier, skills, shift windows, availability |
| Availability | Time-windowed availability per resource/crew |
| Weather | Synthetic condition series affecting constraints |
| Constraints | Capacity, time windows, precedence, policy rules |

### 10.2 Core Entities (Logical Data Model)

| Entity | Key Fields |
|---|---|
| `source` | id, name, reliability_prior |
| `raw_event` | id, source_id, payload, event_time, ingest_time |
| `record` | id, entity_id, type, normalised_payload, version, source_id, event_time, ingest_time, flags |
| `claim` | id, record_id, attribute, value, source_id, observed_at, superseded_by |
| `issue` | id, class (stale/missing/duplicate/conflict), claim_ids, detected_at, status |
| `evidence_edge` | from_id, to_id, relation, timestamp |
| `decision` | id, type, version, created_at, status (verified/stale/invalidated/uncertain) |
| `assumption` | id, decision_id, description, parameters |
| `dependency` | decision_id, input_id, input_version |
| `forecast` | id, target, horizon, mean, interval, calibration_meta, input_versions |
| `schedule` | id, version, assignments, objective_values, solver_meta, parent_schedule_id |
| `agent_run` | id, graph_state, checkpoints, retries, outcome |
| `verification_result` | id, target_id, outcome (verified/invalid/uncertain), violations, uncertainty_flags |
| `approval` | id, target_id, approver, decision, rationale, timestamp |
| `audit_entry` | id, entity, action, before/after refs, actor, timestamp (append-only) |
| `experiment_run` | id, scenario, seed, config, metrics, mlflow_run_id |

### 10.3 Data Rules

- All data is synthetic and generated with seeded generators.
- Every record keeps both event time and ingest time.
- Records are never hard-deleted; supersession and flags are used instead.
- Versioning is mandatory for records, forecasts, schedules, and decisions.
- Raw payloads are retained for provenance.

---

## 11. API Requirements

REST over FastAPI, JSON, Pydantic-validated, versioned under `/api/v1`.

| Area | Representative Endpoints |
|---|---|
| Health | `GET /health` |
| Ingestion (F1) | `POST /ingestion/events`, `GET /ingestion/status`, `GET /ingestion/flagged` |
| Evidence (F2) | `GET /evidence/issues`, `GET /evidence/issues/{id}/autopsy`, `GET /evidence/provenance/{record_id}` |
| Validity (F3) | `GET /validity/decisions`, `GET /validity/decisions/{id}`, `POST /validity/reverify` |
| Forecasts (F4) | `POST /forecasts`, `GET /forecasts/{id}` |
| Planning (F5) | `POST /planning/solve`, `GET /planning/schedules/{id}`, `GET /planning/alternatives` |
| Replanning (F6) | `POST /replanning/run`, `GET /replanning/diff/{old}/{new}` |
| Stress (F7) | `POST /stress/runs`, `GET /stress/runs/{id}` |
| Agents (F8) | `POST /agents/requests`, `GET /agents/requests/{id}`, `GET /agents/requests/{id}/explanation` |
| Verification (F9) | `POST /verification/check`, `GET /verification/{id}` |
| Approvals (F9) | `GET /approvals`, `POST /approvals/{id}/decision` |
| Audit (F9) | `GET /audit`, `GET /audit/{entity}/{id}` (read-only) |
| Benchmarks (F10) | `GET /benchmarks/results`, `GET /benchmarks/ablations` |

**API requirements**

- Consistent error schema with machine-readable codes.
- Idempotency keys for create/solve endpoints.
- Pagination for list endpoints.
- OpenAPI spec auto-generated and exported to `docs/api/openapi.json`.
- TypeScript types kept in parity with Pydantic schemas (contract test).

---

## 12. User Interface Requirements

Next.js + TypeScript + Tailwind; Recharts for visualisation; REST via Fetch.

| Page | Feature | Key Content |
|---|---|---|
| Overview | All | System health, counts by validity status, recent flags, pending approvals. |
| Ingestion | F1 | Stream status, validation errors, flagged records. |
| Evidence | F2 | Issue list; Contradiction Autopsy view with provenance timeline, competing claims, missing info, uncertainty. |
| Validity | F3 | Decision list by status; dependency graph; change history. |
| Forecasts | F4 | Forecast charts with uncertainty bands; calibration indicators. |
| Planning | F5 | Schedule Gantt, objective trade-offs, alternatives. |
| Replanning | F6 | Old vs. new schedule diff, change impact summary. |
| Stress Lab | F7 | Scenario launcher, run results, metrics. |
| Explanations | F8 | Evidence-cited explanations, agent run trace. |
| Approvals | F9 | Queue, approve/reject with rationale. |
| Audit | F9 | Searchable, versioned audit trail. |
| Benchmarks | F10 | Baseline vs. full system, ablations, statistical results. |

**UI requirements**

- Status badges consistently use verified / stale / invalidated / uncertain.
- Uncertainty always visible alongside predictions.
- Every claim or recommendation has a "view evidence" link.
- Loading, empty, and error states for all views.
- Responsive layout (desktop-first, usable on tablet).
- Basic accessibility: keyboard navigation, contrast, semantic labels.

---

## 13. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Performance | Ingestion handles ≥ 1,000 events/sec on a dev machine; API p95 < 500 ms for read endpoints; solver calls bounded by configurable time limits; incremental re-verification faster than full recompute on local changes. |
| Scalability | Kafka partitioning supports horizontal consumer scaling; stateless API containers. |
| Reliability | Idempotent consumers; checkpointed agent workflows; graceful degradation when optional models are unavailable (fall back to baselines). |
| Reproducibility | Seeds, configs, code version, and data version logged per experiment; deterministic runs where feasible. |
| Observability | Structured logs with correlation IDs; metrics for ingestion lag, solver time, verification outcomes; MLflow for experiments. |
| Maintainability | Modular packages per feature; typed Python (mypy) and TypeScript; linting and formatting enforced in CI. |
| Testability | Unit, integration, API, property-based, and e2e tests; ≥ 80% coverage on core services (target). |
| Portability | Full stack runs with `docker compose up`. |
| Security | See §18. |
| Usability | Key flows achievable in few clicks; explanations in plain language with links to evidence. |

---

## 14. Tech Stack

| Category | Technologies |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS, Recharts, REST/Fetch |
| Backend | Python, FastAPI, Pydantic, PostgreSQL, NetworkX, Apache Kafka, Pytest |
| AI / ML | Ditto Transformer, TGN / StrGNN (benchmark candidates), PyMC, DS-DGP (research candidate), PyTorch, GPyTorch, BOCPD, LangGraph, pandas, NumPy, SciPy |
| Optimisation | Google OR-Tools CP-SAT, `alns`, SimPy, Hypothesis |
| Data engineering | Kafka, Python consumers, Pydantic schema validation, PostgreSQL, NetworkX |
| Testing / evaluation | Pytest, Hypothesis, MLflow, SciPy, pandas, NumPy |
| Infrastructure | Docker, Docker Compose, Git + GitHub, any compatible cloud/self-hosted environment |

---

## 15. Evaluation and Benchmarking Plan

### 15.1 Research Questions

| ID | Question |
|---|---|
| RQ1 | Does evidence intelligence (F2) improve detection of stale/missing/conflicting/duplicate data over simple rules? |
| RQ2 | Do temporal graph models (TGN/StrGNN) add value over non-neural baselines? |
| RQ3 | Does incremental re-verification (F3) match full recompute correctness at lower cost? |
| RQ4 | Does DS-DGP give better-calibrated uncertainty than simpler baselines? |
| RQ5 | Does hybrid CP-SAT + ALNS improve objectives over CP-SAT alone within equal time? |
| RQ6 | Does the full system outperform baselines under injected faults (USP 3)? |
| RQ7 | Does independent verification (F9) prevent invalid acceptance without excessive false alarms? |

### 15.2 Baselines

- Naive pipeline (no evidence tracking, no re-validation).
- Rule-based-only data checking.
- Full recomputation on every change.
- CP-SAT only (no ALNS).
- Non-deep forecasting baselines (sparse GP, LSTM, ARIMA).

### 15.3 Ablations

| Ablation | Disabled Component |
|---|---|
| A1 | Evidence intelligence (F2) |
| A2 | Validity tracking / incremental re-verification (F3) |
| A3 | Forecast uncertainty (F4) |
| A4 | ALNS (F5) |
| A5 | Independent verification (F9) |

### 15.4 Experimental Protocol

- Fixed seed sets; multiple repetitions per scenario.
- Scenario matrix: fault type × severity × size.
- Paired comparisons with appropriate statistical tests (e.g., Wilcoxon signed-rank, bootstrap CIs) and effect sizes.
- Report negative results; models that do not beat baselines are not adopted.
- All runs logged to MLflow.

---

## 16. Metrics and KPIs

| Metric | Definition | Feature |
|---|---|---|
| Detection precision / recall | Correct detection of injected data faults | F2, F7 |
| False-alarm rate | Flags raised on clean data / total clean records | F2, F7 |
| Provenance completeness | % of flagged items with full origin chain | F2 |
| Re-verification cost | Nodes/time touched vs. full recompute | F3 |
| Status accuracy | Agreement of incremental vs. full statuses | F3 |
| Forecast error | MAE / RMSE | F4 |
| Calibration | Coverage, ECE, NLL | F4 |
| Feasibility rate | % schedules passing independent verification | F5, F9 |
| Objective quality | Makespan / cost / lateness / robustness | F5 |
| Replan latency & stability | Time to update; % assignments unchanged | F6 |
| Recovery time | Time to return to valid state after fault | F7 |
| Invalid-accept rate | Invalid results approved (target 0) | F9 |
| Approval turnaround | Time in review queue | F9 |
| End-to-end latency | Request → verified result | All |

---

## 17. Testing Strategy

| Level | Tools | Coverage |
|---|---|---|
| Unit | Pytest | Validators, deduplicator, contradiction detector, dependency graph, reverifier, constraint checker, schedule diff |
| Integration | Pytest + test DB/Kafka | Ingestion flow, agent workflow, approval flow |
| API | Pytest + FastAPI test client | All endpoints, error schemas |
| Property-based | Hypothesis | Invariants (e.g., invalid results never accepted; same seed → same run; incremental = full) |
| End-to-end | Pytest / Docker Compose | Kafka → DB → agents → verification → dashboard API |
| Contract | Pytest | TypeScript types ↔ Pydantic schema parity |
| Performance | Pytest | Latency budgets |
| Frontend | ESLint, type check, component tests | Build and critical views |

**CI:** Lint, type check, unit/integration tests on each PR; scheduled benchmark runs optional.

---

## 18. Security, Safety, and Ethics

- **Synthetic data only;** repository includes a data statement and prohibits real operational data.
- **Non-operational:** outputs are research artifacts, not for real-world operational use.
- **Secrets management:** environment variables, `.env.example`, no secrets in Git.
- **Access control:** at minimum API-key or session auth for approval and audit endpoints; roles for approver vs. viewer.
- **Audit integrity:** append-only audit trail; no update/delete endpoints.
- **Input safety:** schema validation on all external input; sanitised prompts to agents; no execution of agent-generated code.
- **LLM safety:** agents constrained by typed schemas, bounded retries, evidence-citation requirement, and non-overridable validators.
- **Dependency hygiene:** pinned versions; routine vulnerability scans.
- **Transparency:** uncertainty and status always displayed; limitations documented.

---

## 19. Deployment and Environments

| Environment | Purpose | Setup |
|---|---|---|
| Local dev | Development and demo | `docker compose up` (frontend, backend, Postgres, Kafka, MLflow) |
| CI | Automated testing | GitHub Actions with service containers |
| Staging / Prod (optional) | Hosted demo | Any compatible cloud or self-hosted environment using the same images |

**Requirements**

- One Dockerfile per service; Compose for orchestration.
- Database migrations via Alembic, run on startup or via script.
- Seed and synthetic data generation scripts.
- Configuration via environment variables with documented defaults.
- Health checks for each service.

---

## 20. Milestones and Delivery Plan

| Phase | Name | Deliverables | Features |
|---|---|---|---|
| 0 | Foundation | Repo, Docker Compose, Postgres, Kafka, CI, config, synthetic data generators | — |
| 1 | Ingestion | Kafka producers/consumers, validation, normalisation, dedup, storage, flagged records | F1 |
| 2 | Verification core | Deterministic validators, audit trail, approval queue | F9 (core) |
| 3 | Planning | CP-SAT model, constraint library, independent check integration; then ALNS | F5 |
| 4 | Evidence intelligence | Evidence graph, issue detection, autopsy, PyMC reliability; TGN/StrGNN benchmark | F2 |
| 5 | Validity | Dependency graph, validity statuses, BOCPD, incremental re-verification | F3 |
| 6 | Prediction | Baselines, then DS-DGP, calibration | F4 |
| 7 | Replanning | Input diff, impact analysis, incremental recompute, schedule diff | F6 |
| 8 | Agentic layer | LangGraph workflow, checkpointing, bounded retries, human approval, explanations | F8 |
| 9 | Stress lab | SimPy twin, fault injectors, scenario library, Hypothesis properties | F7 |
| 10 | Evaluation | Baselines, ablations, statistics, MLflow reports | F10 |
| 11 | Dashboard completion | All pages, polish, accessibility, docs | UI |
| 12 | Hardening | Performance, security review, documentation, final benchmark run | All |

The frontend is built incrementally alongside each backend phase.

**Definition of Done (per feature):** requirements met; unit/integration tests pass; API documented; UI view implemented (where applicable); audit entries emitted; metrics logged; docs updated.

---

## 21. Risks and Mitigations

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Advanced models (TGN/StrGNN, DS-DGP, Ditto) fail to beat simple baselines | Medium | Medium | Treat as candidates; benchmark early; ship baselines; report honestly. |
| R2 | Synthetic data too easy or unrepresentative, inflating results | Medium | High | Diverse generators, harder fault modes, sensitivity analysis, disclosure of limits. |
| R3 | Incremental re-verification diverges from full recompute | Low–Medium | High | Equivalence property tests; fallback to full recompute. |
| R4 | Agents produce unsupported claims | Medium | High | Evidence-citation requirement, schema validation, non-overridable validators. |
| R5 | Scope too large | High | High | Phased plan; P0 first; baselines before advanced models. |
| R6 | Solver performance on larger instances | Medium | Medium | Time limits, ALNS, problem decomposition, incremental re-solve. |
| R7 | Kafka/infra complexity slows development | Medium | Medium | Compose-based local stack, thin abstraction, replayable synthetic producer. |
| R8 | Type drift between frontend and backend | Medium | Low | Generated/contract-tested types. |
| R9 | Reproducibility breaks due to nondeterminism | Medium | Medium | Seed control, pinned dependencies, run metadata in MLflow. |
| R10 | False alarms overwhelm reviewers | Medium | Medium | Threshold tuning, false-alarm metric in evaluation, severity ranking. |

---

## 22. Assumptions, Dependencies, and Open Questions

### 22.1 Assumptions

- Synthetic data can capture the essential failure modes (staleness, conflict, missingness, change).
- Single-tenant, small-team usage; no multi-region requirements.
- GPU is optional; neural components must run (more slowly) on CPU.

### 22.2 Dependencies

- Open-source libraries listed in §14 and their licences.
- An LLM provider or local model for agent/explanation nodes (to be selected).
- Docker-capable development hosts.

### 22.3 Open Questions

| ID | Question | Owner | Needed By |
|---|---|---|---|
| Q1 | Which LLM (hosted vs. local) powers the agent and explanation nodes? | TBD | Phase 8 |
| Q2 | Exact scheduling problem class (e.g., job-shop, RCPSP variants) and instance sizes? | TBD | Phase 3 |
| Q3 | Authentication model and roles required for the demo? | TBD | Phase 2 |
| Q4 | Target false-alarm threshold and detection recall targets? | TBD | Phase 4 |
| Q5 | Is Avro/Schema Registry needed, or is JSON Schema + Pydantic sufficient? | TBD | Phase 1 |
| Q6 | Hosting target for the optional hosted demo? | TBD | Phase 12 |
| Q7 | Which TGN/StrGNN reference implementations to adopt or reimplement? | TBD | Phase 4 |

---

## 23. Out of Scope

- Real operational data, real-world deployment, or integration with real systems.
- Safety-critical or real-time control.
- Fully autonomous decision execution without human approval.
- Multi-tenant SaaS features (billing, org management).
- Mobile native apps.
- Large-scale distributed training.

---

## 24. Glossary

| Term | Definition |
|---|---|
| ALNS | Adaptive Large Neighbourhood Search — metaheuristic that iteratively destroys and repairs solutions. |
| BOCPD | Bayesian Online Change Point Detection — detects distribution shifts in streaming data. |
| CP-SAT | Constraint Programming SAT solver in Google OR-Tools. |
| Contradiction Autopsy | Explanation of why records disagree, with provenance, history, evidence, and missing info. |
| Decision Validity Envelope | Recorded inputs, versions, assumptions, and dependencies under which a decision holds. |
| Ditto | Transformer-based entity-matching model. |
| DS-DGP | Doubly Stochastic Deep Gaussian Process. |
| Ablation | Experiment removing a component to measure its contribution. |
| Digital twin | Simulated environment mirroring the system's domain for testing. |
| Fault injection | Deliberate introduction of faults (missing, stale, conflicting data) into scenarios. |
| HITL | Human-in-the-loop. |
| Provenance | Origin and transformation history of a data item or claim. |
| StrGNN / TGN | Graph neural network families for structural/temporal graphs (benchmark candidates). |
| Verified / Stale / Invalidated / Uncertain | The four validity statuses of a decision. |

---

## 25. Traceability Matrix

| Feature | USP | Workflow Step | Primary Modules | UI Route | Key Metrics |
|---|---|---|---|---|---|
| F1 Ingestion | — | 2, 3 | `streaming/`, `services/ingestion`, `ml/entity_matching` | `/ingestion` | Duplicate rate, flagged count |
| F2 Evidence | USP 1 | 4 | `services/evidence`, `ml/temporal_graph`, `ml/bayesian` | `/evidence` | Detection P/R, false alarms, provenance completeness |
| F3 Validity | USP 2 | 5 | `services/validity`, `ml/change_point` | `/validity` | Re-verify cost, status accuracy |
| F4 Prediction | — | 6 | `services/forecasting`, `ml/forecasting` | `/forecasts` | MAE, calibration |
| F5 Planning | — | 7 | `services/planning`, `optimisation/` | `/planning` | Feasibility, objective quality |
| F6 Replanning | — | 8 | `services/replanning`, `optimisation/incremental` | `/planning/compare` | Replan latency, stability |
| F7 Stress Lab | USP 3 | 9 | `simulation/` | `/stress-lab` | Detection, recovery, failure rate |
| F8 Agentic AI | — | 10 | `agents/`, `services/explanation` | `/explanations` | Evidence-citation rate, retry counts |
| F9 Verification & Audit | — | 11 | `services/verification`, `services/audit` | `/approvals`, `/audit` | Invalid-accept rate (0), turnaround |
| F10 Benchmarking | — | 12 | `evaluation/`, `services/benchmarking` | `/benchmarks` | Effect sizes, CIs |

---

*End of document.*
