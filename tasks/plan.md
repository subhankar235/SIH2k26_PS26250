# Implementation Plan: Dynamic Air Operations & Resource Optimisation (MAGI Architecture)

## Overview
This plan implements the complete end-to-end multi-service architecture for SIH Problem Statement 26250. It establishes a decoupled JavaScript Ingestion Gateway streaming operational events into Apache Kafka, an autonomous Python MAGI Multi-Agent Consortium backed by Google OR-Tools CP-SAT and predictive models, PostgreSQL for persistent auditability, an event disruption simulator, and real-time streaming for the operational command dashboard.

## Architecture Decisions
- **Decoupled Runtimes:** JavaScript/Express handles perimeter API ingestion and Kafka event publishing; Python 3.11+ hosts the MAGI agent network, ML predictive models, and Google OR-Tools CP-SAT constraint solver.
- **Negotiation-First / Warm-Start Loop:** The 5 domain agents autonomously negotiate allocations and counter-proposals based on domain constraints, passing an agreed candidate seed (`model.AddHint`) to OR-Tools CP-SAT to mathematically verify feasibility and fine-tune Pareto optimality.
- **Deterministic Core with Optional SLM Reasoning:** Domain decisions, bids, and constraint checks are 100% deterministic; an optional local SLM (or template fallback) generates tactical explanations for the MAGI visualizer.
- **Topological Corridor Graph:** Airspace and threat environments are modeled as discrete route corridors with dynamic threat coefficients and weather status.
- **Equilibrium-Break Replanning:** Streaming Kafka events are debounced with a 1-second sliding batch window; any breach of active flight constraints breaks equilibrium and triggers an automatic peer renegotiation and replanning cycle.

---

## Task List

### Phase 1: Infrastructure & Ingestion Gateway
- [ ] **Task 1: Infrastructure Scaffolding (`docker-compose.yml`)**  
  Configure Apache Kafka, Zookeeper, and PostgreSQL services with persistent volumes and health checks.
- [ ] **Task 2: Ingestion Gateway Alignment (`services/ingestion`)**  
  Update Node.js/Express ingestion API to support the defense logistics schema (`aircraft`, `crew`, `payload`, `weather`, `threats`) streaming to domain Kafka topics (`air.*`).
- [ ] **Task 3: PostgreSQL Persistence Layer (`services/agent_engine/src/storage`)**  
  Create async PostgreSQL schema and SQLAlchemy models for operational events, versioned mission plans, and agent negotiation transcripts.

### Checkpoint 1: Infrastructure & Ingestion
- [ ] Docker Compose starts Kafka and PostgreSQL cleanly.
- [ ] Ingestion API validates payload and threat events and publishes to Kafka.
- [ ] PostgreSQL tables initialize without errors.

---

### Phase 2: Operations Research Engine & Predictive Models
- [ ] **Task 4: Python Project Scaffolding (`services/agent_engine`)**  
  Initialize Python project with `pyproject.toml`, FastAPI, Google OR-Tools, aiokafka, Pydantic v2, and testing harness (`pytest`).
- [ ] **Task 5: Google OR-Tools CP-SAT Solver (`services/agent_engine/src/solver`)**  
  Implement the discrete multi-objective air operations model: maximizing served priority, minimizing corridor threat exposure, minimizing schedule churn, and satisfying airframe range and crew duty constraints.
- [ ] **Task 6: Domain Predictive Models (`services/agent_engine/src/models`)**  
  Implement Python predictive models: Fleet turnaround predictor, Weather degradation trend estimator, and Airspace corridor risk scorer.

### Checkpoint 2: Mathematical Solver & Predictive Models
- [ ] Unit tests verify CP-SAT solver finds optimal solutions and detects infeasibilities.
- [ ] Predictive models generate bounded numerical features for the agents.

---

### Phase 3: Autonomous MAGI Multi-Agent Consortium
- [ ] **Task 7: Domain Specialist Agents (`services/agent_engine/src/agents`)**  
  Implement the 5 specialized domain agents (Fleet, Crew, Payload, Airspace/Threat, Weather) with deterministic rule engines, constraint checks, and utility bidding.
- [ ] **Task 8: MAGI Peer-Negotiation Protocol & Coordinator (`services/agent_engine/src/negotiation`)**  
  Build the multi-round negotiation protocol: candidate proposals, objections, counter-bids, and unanimous consensus formation feeding warm-start seeds into CP-SAT.
- [ ] **Task 9: Tactical Rationale Synthesizer (`services/agent_engine/src/llm`)**  
  Implement the explanation module generating tactical MAGI debate transcripts using a local SLM (via Ollama) with transparent deterministic template fallback.

### Checkpoint 3: Multi-Agent Consensus
- [ ] Negotiation protocol converges to feasible candidate seeds across test scenarios.
- [ ] Objections (e.g., threat spike in corridor) trigger valid counter-proposals.
- [ ] CP-SAT validates and proves the final consensus plan.

---

### Phase 4: Dynamic Replanning & Disruption Simulator
- [ ] **Task 10: Kafka Event Consumer & Equilibrium Engine (`services/agent_engine/src/transport`)**  
  Implement asynchronous Kafka consumers with 1-second debouncing, equilibrium-break detection, and automatic renegotiation dispatch.
- [ ] **Task 11: Operational Disruption Simulator (`services/simulator`)**  
  Build the scenario injection CLI supporting pre-scripted disruptions (Hostile SAM threat alert, Convective storm front, Unscheduled airframe maintenance) and manual REST triggers.
- [ ] **Task 12: Real-time Streaming API (`services/agent_engine/src/api`)**  
  Build FastAPI WebSocket and REST endpoints exposing live telemetry, active plans, and real-time MAGI agent thought/debate streams to the frontend.

### Checkpoint 4: End-to-End System Integration
- [ ] Simulator injects disruption -> Ingestion publishes to Kafka -> Python engine detects equilibrium break -> Agents renegotiate -> CP-SAT optimizes -> Updated plan and debate stream over WebSocket.
- [ ] System recovery survives broker and service restarts.

---

## Risks and Mitigations
| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **Kafka / Solver Event Thrashing** | High | Implement a 1-second sliding debounce window to batch telemetry events before declaring an equilibrium break. |
| **Agent Deadlock / Non-convergence** | Medium | Bounded negotiation rounds (default 4 rounds) with Coordinator fallback to CP-SAT global relaxation. |
| **Local SLM Latency / Unavailability** | Low | Decision logic is 100% deterministic; SLM is strictly used for text reasoning traces with instant template fallback. |

