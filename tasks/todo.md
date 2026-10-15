# Task List: Dynamic Air Operations & Resource Optimisation (MAGI Architecture)

## Phase 1: Infrastructure & Ingestion Gateway

### Task 1: Infrastructure Scaffolding (`docker-compose.yml`)
**Description:** Configure Docker Compose with Apache Kafka, Zookeeper, and PostgreSQL services, including persistent volumes and health checks.
**Acceptance criteria:**
- [ ] `docker-compose.yml` configures Kafka broker, Zookeeper, and PostgreSQL 16.
- [ ] Service health checks ensure Kafka and PostgreSQL are ready before dependents connect.
- [ ] Ports exposed: Kafka (9092), PostgreSQL (5432).
**Verification:**
- [ ] `docker compose config` validates without errors.
**Dependencies:** None
**Files touched:** `docker-compose.yml`
**Estimated scope:** Small (1 file)

### Task 2: Ingestion Gateway Alignment (`services/ingestion`)
**Description:** Update Node.js/Express ingestion API to support the defense logistics schema (`aircraft`, `crew`, `payload`, `weather`, `threats`) streaming to domain Kafka topics (`air.*`).
**Acceptance criteria:**
- [ ] Ingestion contracts validate defense air operations events (`air.fleet`, `air.crew`, `air.payload`, `air.weather`, `air.threats`).
- [ ] Express endpoints accept authenticated POST requests and produce to the correct Kafka topic via outbox.
- [ ] Stale data, sequence gaps, and unauthorized sources are rejected or flagged.
**Verification:**
- [ ] `npm --prefix services/ingestion test` passes existing ingestion suite.
- [ ] Unit tests verify new threat and payload schemas.
**Dependencies:** Task 1
**Files touched:**
- `services/ingestion/src/contracts/events.js`
- `services/ingestion/src/app.js`
- `services/ingestion/test/http.test.js`
**Estimated scope:** Medium (3 files)

### Task 3: PostgreSQL Persistence Layer (`services/agent_engine/src/storage`)
**Description:** Create async PostgreSQL schema and SQLAlchemy models for operational events, versioned mission plans, and agent negotiation transcripts.
**Acceptance criteria:**
- [ ] Async SQLAlchemy models defined for `OperationalEvent`, `MissionPlan`, and `NegotiationTranscript`.
- [ ] Async engine, session management, and auto-table creation on startup.
- [ ] CRUD functions for recording events, updating plans, and storing negotiation logs.
**Verification:**
- [ ] Pytest suite verifies DB creation, insertion, and retrieval using in-memory SQLite / PostgreSQL.
**Dependencies:** Task 1
**Files touched:**
- `services/agent_engine/src/storage/database.py`
- `services/agent_engine/src/storage/models.py`
- `services/agent_engine/tests/test_storage.py`
**Estimated scope:** Medium (3 files)

---

## Checkpoint 1: Infrastructure & Ingestion
- [ ] Kafka broker and PostgreSQL services launch cleanly via Docker.
- [ ] Ingestion API validates payload and threat events and publishes to Kafka.
- [ ] Database schema initializes and stores test records.

---

## Phase 2: Operations Research Engine & Predictive Models

### Task 4: Python Project Scaffolding (`services/agent_engine`)
**Description:** Initialize Python package with `pyproject.toml`, FastAPI, Google OR-Tools, aiokafka, Pydantic v2, and pytest suite.
**Acceptance criteria:**
- [ ] `pyproject.toml` or `requirements.txt` specifies all runtime dependencies (`ortools`, `fastapi`, `uvicorn`, `aiokafka`, `pydantic`, `sqlalchemy`, `asyncpg`, `scikit-learn`).
- [ ] Package structure created under `services/agent_engine/src/`.
- [ ] Pytest configured and executing clean baseline test.
**Verification:**
- [ ] `pytest services/agent_engine/tests` runs and passes.
**Dependencies:** None
**Files touched:**
- `services/agent_engine/pyproject.toml`
- `services/agent_engine/requirements.txt`
- `services/agent_engine/src/__init__.py`
**Estimated scope:** Small (2-3 files)

### Task 5: Google OR-Tools CP-SAT Solver (`services/agent_engine/src/solver`)
**Description:** Implement the discrete multi-objective air operations model: maximizing served priority, minimizing corridor threat exposure, minimizing schedule churn, and satisfying airframe range and crew duty constraints.
**Acceptance criteria:**
- [ ] CP-SAT model creates integer/boolean variables for aircraft-mission-slot-corridor assignments.
- [ ] Enforces hard constraints: range, payload weight, turnaround time, crew duty limit, corridor weather/threat threshold, base capacity.
- [ ] Multi-objective function penalizes threat exposure and schedule churn while maximizing priority.
- [ ] Accepts warm-start candidate seeds (`model.AddHint`) and returns diagnostic slack upon infeasibility.
**Verification:**
- [ ] Unit tests solve standard 5-mission and 10-mission benchmarks in <500ms.
- [ ] Infeasibility tests verify correct conflict detection.
**Dependencies:** Task 4
**Files touched:**
- `services/agent_engine/src/solver/model.py`
- `services/agent_engine/src/solver/optimizer.py`
- `services/agent_engine/tests/test_solver.py`
**Estimated scope:** Medium (3 files)

### Task 6: Domain Predictive Models (`services/agent_engine/src/models`)
**Description:** Implement Python predictive models: Fleet turnaround predictor, Weather degradation trend estimator, and Airspace corridor risk scorer.
**Acceptance criteria:**
- [ ] Turnaround model estimates turnaround minutes and delay risk based on airframe utilization and weather.
- [ ] Weather trend model estimates probability of weather falling below operating minima.
- [ ] Threat risk scorer computes corridor risk indices from radar and intel reports.
**Verification:**
- [ ] Unit tests verify model inference outputs valid bounded numeric features.
**Dependencies:** Task 4
**Files touched:**
- `services/agent_engine/src/models/turnaround.py`
- `services/agent_engine/src/models/weather_trend.py`
- `services/agent_engine/src/models/threat_scorer.py`
- `services/agent_engine/tests/test_models.py`
**Estimated scope:** Medium (4 files)

---

## Checkpoint 2: Mathematical Solver & Predictive Models
- [ ] All solver tests pass; solver computes proven optimal schedules and rejects infeasible assignments.
- [ ] Predictive models generate valid numeric inputs for downstream agents.

---

## Phase 3: Autonomous MAGI Multi-Agent Consortium

### Task 7: Domain Specialist Agents (`services/agent_engine/src/agents`)
**Description:** Implement the 5 specialized domain agents (Fleet, Crew, Payload, Airspace/Threat, Weather) with deterministic rule engines, constraint checks, and utility bidding.
**Acceptance criteria:**
- [ ] FleetAgent, CrewAgent, PayloadAgent, ThreatAgent, WeatherAgent inherit from base `MagiAgent`.
- [ ] Each agent implements `evaluate_proposal(candidate)` and `generate_counter_bid(rejection)`.
- [ ] Bids and objections strictly reflect domain constraints and predictive model scores.
**Verification:**
- [ ] Unit tests verify agents raise appropriate objections (e.g., ThreatAgent rejects corridor with high threat score).
**Dependencies:** Task 5, Task 6
**Files touched:**
- `services/agent_engine/src/agents/base.py`
- `services/agent_engine/src/agents/specialists.py`
- `services/agent_engine/tests/test_agents.py`
**Estimated scope:** Medium (3 files)

### Task 8: MAGI Peer-Negotiation Protocol & Coordinator (`services/agent_engine/src/negotiation`)
**Description:** Build the multi-round negotiation protocol: candidate proposals, objections, counter-bids, and unanimous consensus formation feeding warm-start seeds into CP-SAT.
**Acceptance criteria:**
- [ ] Coordinator coordinates bounded negotiation rounds (default max 4 rounds).
- [ ] Peer-to-peer message exchange: `PROPOSAL`, `ACCEPT`, `OBJECTION`, `COUNTER_BID`.
- [ ] Unanimous consensus converts into a warm-start seed for the OR-Tools solver.
- [ ] If solver reports infeasibility, Coordinator triggers iterative relaxation loop.
**Verification:**
- [ ] Unit tests simulate negotiation convergence and conflict resolution across multiple test scenarios.
**Dependencies:** Task 7
**Files touched:**
- `services/agent_engine/src/negotiation/protocol.py`
- `services/agent_engine/src/negotiation/coordinator.py`
- `services/agent_engine/tests/test_negotiation.py`
**Estimated scope:** Medium (3 files)

### Task 9: Tactical Rationale Synthesizer (`services/agent_engine/src/llm`)
**Description:** Implement the explanation module generating tactical MAGI debate transcripts using a local SLM (via Ollama) with transparent deterministic template fallback.
**Acceptance criteria:**
- [ ] SLM prompt runner formats agent bids and objections into tactical dialogue (e.g., MAGI Melchior/Balthasar style).
- [ ] Automatic fallback to deterministic templates if Ollama is unreachable or timeout occurs (<2s).
- [ ] Output includes structured thought logs, confidence scores, and unanimous consensus summary.
**Verification:**
- [ ] Unit tests verify fallback templates produce valid transcripts without Ollama.
**Dependencies:** Task 8
**Files touched:**
- `services/agent_engine/src/llm/synthesizer.py`
- `services/agent_engine/src/llm/templates.py`
- `services/agent_engine/tests/test_synthesizer.py`
**Estimated scope:** Small (3 files)

---

## Checkpoint 3: Multi-Agent Consensus
- [ ] Negotiation protocol converges to verified candidate plans.
- [ ] Threat, weather, and maintenance objections trigger correct counter-proposals.
- [ ] Solver proves optimality of the negotiated plan.

---

## Phase 4: Dynamic Replanning & Disruption Simulator

### Task 10: Kafka Event Consumer & Equilibrium Engine (`services/agent_engine/src/transport`)
**Description:** Implement asynchronous Kafka consumers with 1-second debouncing, equilibrium-break detection, and automatic renegotiation dispatch.
**Acceptance criteria:**
- [ ] `aiokafka` consumer reads from `air.*` topics.
- [ ] 1-second sliding debounce batches incoming events to prevent solver thrashing.
- [ ] Equilibrium-break detector identifies constraint breaches on active flights.
- [ ] Automatically triggers Coordinator renegotiation upon equilibrium break.
**Verification:**
- [ ] Tests verify debouncing batches burst events; disruption event triggers replan.
**Dependencies:** Task 2, Task 8
**Files touched:**
- `services/agent_engine/src/transport/consumer.py`
- `services/agent_engine/src/transport/equilibrium.py`
- `services/agent_engine/tests/test_transport.py`
**Estimated scope:** Medium (3 files)

### Task 11: Operational Disruption Simulator (`services/simulator`)
**Description:** Build the scenario injection CLI supporting pre-scripted disruptions (Hostile SAM threat alert, Convective storm front, Unscheduled airframe maintenance) and manual REST triggers.
**Acceptance criteria:**
- [ ] Simulator CLI loads YAML/JSON scenario definitions.
- [ ] Scripts: `baseline.json`, `threat_alert.json`, `storm_front.json`, `mechanical_fault.json`.
- [ ] CLI command `python -m simulator.injector --scenario <name>` posts events into Ingestion API.
**Verification:**
- [ ] Running simulator posts valid events and receives HTTP 202/200 receipts.
**Dependencies:** Task 2
**Files touched:**
- `services/simulator/scenarios/baseline.json`
- `services/simulator/scenarios/disruptions.json`
- `services/simulator/injector.py`
- `services/simulator/requirements.txt`
**Estimated scope:** Medium (4 files)

### Task 12: Real-time Streaming API (`services/agent_engine/src/api`)
**Description:** Build FastAPI WebSocket and REST endpoints exposing live telemetry, active plans, and real-time MAGI agent thought/debate streams to the frontend.
**Acceptance criteria:**
- [ ] `GET /api/v1/plans/active` returns the current equilibrium plan and assignments.
- [ ] `GET /api/v1/telemetry/status` returns data source health and corridor states.
- [ ] `WS /ws/magi/stream` streams live agent debate messages, votes, and replan events.
**Verification:**
- [ ] WebSocket test client connects and receives live negotiation events.
**Dependencies:** Task 8, Task 10
**Files touched:**
- `services/agent_engine/src/api/server.py`
- `services/agent_engine/src/api/routes.py`
- `services/agent_engine/src/api/websocket.py`
- `services/agent_engine/tests/test_api.py`
**Estimated scope:** Medium (4 files)

---

## Checkpoint 4: End-to-End System Integration
- [ ] End-to-end flow: Simulator injects event -> Ingestion publishes to Kafka -> Python engine detects equilibrium break -> Agents renegotiate -> OR-Tools optimizes -> New plan published to DB and streamed via WebSocket.
- [ ] System handles continuous disruptions gracefully with anti-churn schedule stability.
