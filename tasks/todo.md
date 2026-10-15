# Task List: Dynamic Air Operations & Resource Optimisation (MAGI Architecture)

## Phase 1: Infrastructure & Ingestion Gateway

### Task 1: Infrastructure Scaffolding (`docker-compose.yml`)
**Description:** Configure Docker Compose with Apache Kafka, Zookeeper, and PostgreSQL services, including persistent volumes and health checks.
**Acceptance criteria:**
- [x] `docker-compose.yml` configures Kafka broker, Zookeeper/KRaft, and PostgreSQL 16.
- [x] Service health checks ensure Kafka and PostgreSQL are ready before dependents connect.
- [x] Ports exposed: Kafka (29092), PostgreSQL (5432).
**Verification:**
- [x] `docker compose config` validates without errors.
- [x] Both containers running and healthy.
**Dependencies:** None
**Files touched:** `docker-compose.yml`
**Status:** [COMPLETED]

### Task 2: Ingestion Gateway Alignment (`services/ingestion`)
**Description:** Update Node.js/Express ingestion API to support the defense logistics schema (`aircraft`, `crew`, `payload`, `weather`, `threats`) streaming to domain Kafka topics (`air.*`).
**Acceptance criteria:**
- [x] Ingestion contracts validate defense air operations events (`air.fleet`, `air.crew`, `air.payload`, `air.weather`, `air.threats`).
- [x] Express endpoints accept authenticated POST requests and produce to the correct Kafka topic via outbox.
- [x] Stale data, sequence gaps, and unauthorized sources are rejected or flagged.
**Verification:**
- [x] `npm --prefix services/ingestion test` passes 201 tests (100%).
- [x] Syntax check passes 77 JavaScript files.
- [x] Generated contracts check passes.
**Dependencies:** Task 1
**Status:** [COMPLETED]

### Task 3: PostgreSQL Persistence Layer (`services/agent_engine/src/storage`)
**Description:** Create async PostgreSQL schema and SQLAlchemy models for operational events, versioned mission plans, and agent negotiation transcripts.
**Acceptance criteria:**
- [x] Async SQLAlchemy models defined for `OperationalEvent`, `MissionPlan`, and `NegotiationTranscript`.
- [x] Async engine, session management, and auto-table creation on startup.
- [x] CRUD functions for recording events, updating plans, and storing negotiation logs.
**Verification:**
- [x] Pytest suite verifies DB creation, insertion, and retrieval using live PostgreSQL container.
**Dependencies:** Task 1
**Files touched:**
- `services/agent_engine/src/storage/database.py`
- `services/agent_engine/src/storage/models.py`
- `services/agent_engine/tests/test_storage.py`
**Status:** [COMPLETED]

---

## Checkpoint 1: Infrastructure & Ingestion
- [x] Kafka broker and PostgreSQL services launch cleanly via Docker.
- [x] Ingestion API validates payload and threat events and publishes to Kafka.
- [x] Database schema initializes and stores test records.

---

## Phase 2: Operations Research Engine & Predictive Models

### Task 4: Python Project Scaffolding (`services/agent_engine`)
**Description:** Initialize Python package with `pyproject.toml`, FastAPI, Google OR-Tools, aiokafka, Pydantic v2, and pytest suite.
**Acceptance criteria:**
- [x] `pyproject.toml` or `requirements.txt` specifies all runtime dependencies (`ortools`, `fastapi`, `uvicorn`, `aiokafka`, `pydantic`, `sqlalchemy`, `asyncpg`, `scikit-learn`).
- [x] Package structure created under `services/agent_engine/src/`.
- [x] Pytest configured and executing clean baseline test.
**Verification:**
- [x] `pytest services/agent_engine/tests` runs and passes.
**Dependencies:** None
**Files touched:**
- `services/agent_engine/pyproject.toml`
- `services/agent_engine/requirements.txt`
- `services/agent_engine/src/__init__.py`
**Status:** [COMPLETED]

### Task 5: Google OR-Tools CP-SAT Solver (`services/agent_engine/src/solver`)
**Description:** Implement the discrete multi-objective air operations model: maximizing served priority, minimizing corridor threat exposure, minimizing schedule churn, and satisfying airframe range and crew duty constraints.
**Acceptance criteria:**
- [x] CP-SAT model creates integer/boolean variables for aircraft-mission-slot-corridor assignments.
- [x] Enforces hard constraints: range, payload weight, turnaround time, crew duty limit, corridor weather/threat threshold, base capacity.
- [x] Multi-objective function penalizes threat exposure and schedule churn while maximizing priority.
- [x] Accepts warm-start candidate seeds (`model.AddHint`) and returns diagnostic slack upon infeasibility.
**Verification:**
- [x] Unit tests solve standard 5-mission and 10-mission benchmarks in <500ms.
- [x] Infeasibility tests verify correct conflict detection.
**Dependencies:** Task 4
**Files touched:**
- `services/agent_engine/src/solver/model.py`
- `services/agent_engine/src/solver/optimizer.py`
- `services/agent_engine/tests/test_solver.py`
**Status:** [COMPLETED]

### Task 6: Domain Predictive Models (`services/agent_engine/src/models`)
**Description:** Implement Python predictive models: Fleet turnaround predictor, Weather degradation trend estimator, and Airspace corridor risk scorer.
**Acceptance criteria:**
- [x] Turnaround model estimates turnaround minutes and delay risk based on airframe utilization and weather.
- [x] Weather trend model estimates probability of weather falling below operating minima.
- [x] Threat risk scorer computes corridor risk indices from radar and intel reports.
**Verification:**
- [x] Unit tests verify model inference outputs valid bounded numeric features.
**Dependencies:** Task 4
**Files touched:**
- `services/agent_engine/src/models/turnaround.py`
- `services/agent_engine/src/models/weather_trend.py`
- `services/agent_engine/src/models/threat_scorer.py`
- `services/agent_engine/tests/test_models.py`
**Status:** [COMPLETED]

---

## Checkpoint 2: Mathematical Solver & Predictive Models
- [x] All solver tests pass; solver computes proven optimal schedules and rejects infeasible assignments.
- [x] Predictive models generate valid numeric inputs for downstream agents.

---

## Phase 3: Autonomous MAGI Multi-Agent Consortium

### Task 7: Domain Specialist Agents (`services/agent_engine/src/agents`)
**Description:** Implement the 5 specialized domain agents (Fleet, Crew, Payload, Airspace/Threat, Weather) with deterministic rule engines, constraint checks, and utility bidding.
**Acceptance criteria:**
- [x] FleetAgent, CrewAgent, PayloadAgent, ThreatAgent, WeatherAgent inherit from base `BaseMagiAgent`.
- [x] Each agent implements `evaluate_candidate(mission, airframe, crew, corridor, slot)`.
- [x] Bids and objections strictly reflect domain constraints and predictive model scores.
**Verification:**
- [x] Unit tests verify agents raise appropriate objections (e.g., ThreatAgent rejects corridor with high threat score).
**Dependencies:** Task 5, Task 6
**Files touched:**
- `services/agent_engine/src/agents/base.py`
- `services/agent_engine/src/agents/specialists.py`
**Status:** [COMPLETED]

### Task 8: MAGI Peer-Negotiation Protocol & Coordinator (`services/agent_engine/src/negotiation`)
**Description:** Build the multi-round negotiation protocol: candidate proposals, objections, counter-bids, and unanimous consensus formation feeding warm-start seeds into CP-SAT.
**Acceptance criteria:**
- [x] Coordinator coordinates bounded negotiation rounds (default max 4 rounds).
- [x] Peer-to-peer message exchange: `PROPOSAL`, `ACCEPT`, `OBJECTION`, `COUNTER_BID`.
- [x] Unanimous consensus converts into a warm-start seed for the OR-Tools solver.
- [x] If solver reports infeasibility, Coordinator triggers iterative relaxation loop.
**Verification:**
- [x] Unit tests simulate negotiation convergence and conflict resolution across multiple test scenarios.
**Dependencies:** Task 7
**Files touched:**
- `services/agent_engine/src/negotiation/protocol.py`
- `services/agent_engine/src/negotiation/coordinator.py`
- `services/agent_engine/tests/test_negotiation.py`
**Status:** [COMPLETED]

### Task 9: Tactical Rationale Synthesizer (`services/agent_engine/src/llm`)
**Description:** Implement the explanation module generating tactical MAGI debate transcripts using a local SLM (via Ollama) with transparent deterministic template fallback.
**Acceptance criteria:**
- [x] SLM prompt runner formats agent bids and objections into tactical dialogue (e.g., MAGI Melchior/Balthasar style).
- [x] Automatic fallback to deterministic templates if Ollama is unreachable or timeout occurs (<2s).
- [x] Output includes structured thought logs, confidence scores, and unanimous consensus summary.
**Verification:**
- [x] Unit tests verify fallback templates produce valid transcripts without Ollama.
**Dependencies:** Task 8
**Files touched:**
- `services/agent_engine/src/llm/synthesizer.py`
- `services/agent_engine/src/llm/templates.py`
- `services/agent_engine/tests/test_synthesizer.py`
**Status:** [COMPLETED]

---

## Checkpoint 3: Multi-Agent Consensus
- [x] Negotiation protocol converges to verified candidate plans.
- [x] Threat, weather, and maintenance objections trigger correct counter-proposals.
- [x] Solver proves optimality of the negotiated plan.

---

## Phase 4: Dynamic Replanning & Disruption Simulator

### Task 10: Kafka Event Consumer & Equilibrium Engine (`services/agent_engine/src/transport`)
**Description:** Implement asynchronous Kafka consumers with 1-second debouncing, equilibrium-break detection, and automatic renegotiation dispatch.
**Acceptance criteria:**
- [x] `aiokafka` consumer reads from domain topics.
- [x] 1-second sliding debounce batches incoming events to prevent solver thrashing.
- [x] Equilibrium-break detector identifies constraint breaches on active flights.
- [x] Automatically triggers Coordinator renegotiation upon equilibrium break.
**Verification:**
- [x] Tests verify debouncing batches burst events; disruption event triggers replan.
**Dependencies:** Task 2, Task 8
**Files touched:**
- `services/agent_engine/src/transport/consumer.py`
- `services/agent_engine/src/transport/equilibrium.py`
- `services/agent_engine/tests/test_transport.py`
**Status:** [COMPLETED]

### Task 11: Operational Disruption Simulator (`services/simulator`)
**Description:** Build the scenario injection CLI supporting pre-scripted disruptions (Hostile SAM threat alert, Convective storm front, Unscheduled airframe maintenance) and manual REST triggers.
**Acceptance criteria:**
- [x] Simulator CLI loads YAML/JSON scenario definitions.
- [x] Scripts: `threat_spike.json`, `storm_front.json`, `mechanical_fault.json`.
- [x] CLI script `injector.py` posts events into Ingestion API with valid bearer tokens.
**Verification:**
- [x] Unit tests verify scenario file schemas and token loading.
**Dependencies:** Task 2
**Files touched:**
- `services/simulator/scenarios/threat_spike.json`
- `services/simulator/scenarios/storm_front.json`
- `services/simulator/scenarios/mechanical_fault.json`
- `services/simulator/injector.py`
- `services/simulator/requirements.txt`
**Status:** [COMPLETED]

### Task 12: Real-time Streaming API (`services/agent_engine/src/api`)
**Description:** Build FastAPI WebSocket and REST endpoints exposing live telemetry, active plans, and real-time MAGI agent thought/debate streams to the frontend.
**Acceptance criteria:**
- [x] `GET /api/v1/plans/active` returns the current equilibrium plan and assignments.
- [x] `GET /api/v1/status` returns data source health, revision, and active flight counts.
- [x] `WS /ws/magi/stream` streams live agent debate messages, votes, and replan events.
**Verification:**
- [x] AsyncClient tests verify health, status, active plan, and replan endpoints.
**Dependencies:** Task 8, Task 10
**Files touched:**
- `services/agent_engine/src/api/server.py`
- `services/agent_engine/src/api/routes.py`
- `services/agent_engine/src/api/websocket.py`
- `services/agent_engine/tests/test_api.py`
**Status:** [COMPLETED]

---

## Checkpoint 4: End-to-End System Integration
- [x] End-to-end flow: Simulator injects event -> Ingestion publishes to Kafka -> Python engine detects equilibrium break -> Agents renegotiate -> OR-Tools optimizes -> New plan published to DB and streamed via WebSocket.
- [x] System handles continuous disruptions gracefully with anti-churn schedule stability.
