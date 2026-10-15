# Dynamic Air Operations & Resource Optimisation Decision-Support System (MAGI Architecture)
## System Design Document — SIH Problem Statement ID: 26250

**Document Version:** 2.0 (Post-Review Consolidation)  
**Date:** 2026-10-15  
**Status:** Ready for Final Approval  

---

## 1. Intent and The Why

### 1.1 Operational Context
In contested and fast-evolving air operational environments (SIH PS26250 - Ministry of Defence / Defence Services Staff College), mission planners face severe challenges in real-time tactical decision making. Critical operational parameters—aircraft availability, aircrew duty cycles and qualifications, weapon loads and mission-critical payloads, airspace restrictions, real-time threat levels, and weather conditions—are managed across separate, disconnected systems. 

When unexpected disruptions occur (e.g., sudden convective storms, incoming surface/air threats, airframe maintenance failures), planners lack a unified real-time decision-support framework. Manually re-evaluating constraints and retasking assets takes valuable hours and results in suboptimal resource allocation.

### 1.2 Core Vision & Architecture
This project implements an end-to-end, real-time decision-support system composed of decoupled services:
1. **Multi-Source Ingestion Gateway (JavaScript / Express / Kafka):** Ingests, validates, and streams operational telemetry into domain Kafka topics.
2. **Autonomous MAGI Multi-Agent Consortium (Python):** Specialized domain agents (Fleet, Crew, Payload, Airspace/Threat, Weather) operating in an interconnected peer-negotiation network.
3. **Operations Research Constraint Solver (Google OR-Tools CP-SAT):** Evaluates mathematical feasibility, validates agent commitments, and optimizes multi-objective schedules.
4. **Dynamic Equilibrium & Replanning Engine:** Automatically triggers renegotiation when live disruption events break current operational equilibrium.
5. **Interactive Command Dashboard & Disruption Simulator:** A tactical operational map and a MAGI agent network visualizer driven by on-demand event injection.

---

## 2. Settled Decisions & Architectural Choices

### 2.1 Agent Dialogue & Intelligence Model (Hybrid Architecture)
* **Deterministic Core for Decision-Taking:** All domain calculations, feasibility checks, bidding utilities, and voting rules are executed **100% deterministically in Python**. This guarantees mathematical validity, sub-second execution, zero hallucination of flight boundaries, and complete audit reproducibility.
* **Pluggable Small Language Model (SLM) for Rich Debate:** An optional local SLM (e.g., Qwen 2.5 1.5B/3B or Gemma via Ollama) enriches agent debates, synthesizing tactical trade-offs and generating natural-language arguments for the MAGI visualizer.
* **Deterministic Fallback:** If the local LLM is disabled or unavailable, the system transparently falls back to structured, deterministic rationale templates with zero impact on operational decisions.

### 2.2 MAGI Consensus & Solver Workflow (Negotiation-First / Warm-Start Loop)
* **Phase 1 (Autonomous Peer Negotiation):** The 5 domain agents review current operational telemetry, formulate bids, raise objections (e.g., *CrewAgent rejects night flight for uncertified crew; ThreatAgent objects to Corridor Alpha due to active radar*), and negotiate counter-proposals to converge on a unanimous candidate allocation.
* **Phase 2 (Solver Verification & Proof):** The agreed candidate plan is passed as a warm-start seed (`model.AddHint(...)`) to **Google OR-Tools CP-SAT**.
* **Phase 3 (Optimization & Hard Proof):** CP-SAT mathematically verifies all global constraints (fuel burn, airbase runway capacities, turnaround times, cumulative crew duty hours) and proves Pareto optimality.
* **Phase 4 (Iterative Relaxation Loop):** If CP-SAT detects an infeasibility in the agents' candidate seed, it returns diagnostic slack conflicts to the Coordinator. The Coordinator prompts the specific conflicting agents to relax non-critical constraints or negotiate an alternate corridor/slot.

### 2.3 Mission Scope & Modeling
* Grounded in the SIH theme (*Transportation & Logistics*): Tactical air mobility, emergency relief transport, high-priority ordnance/payload delivery, and medevac taskings.
* Each mission defines: Origin airbase, Destination airbase, Payload/Ordnance requirements (weight, category, hazardous/cold-chain constraints), Aircrew qualification requirements, Priority score (1–10), and Strict Time Window (earliest departure, deadline).

### 2.4 Airspace, Threat, and Weather Modeling
* Modeled as a **discrete topological network of flight corridors** connecting airbases and operational sectors (e.g., *Corridor Alpha, Bravo, Charlie*).
* Each corridor carries dynamic attributes: Distance/Flight Time, Weather Status (Clear, Moderate, Storm/No-Fly), and Threat Risk Coefficient (0.0 = Safe, 1.0 = Contested/Air Defense Umbrella).
* Allows OR-Tools CP-SAT to mathematically penalize high-risk corridors and minimize threat exposure while selecting safe alternatives.

### 2.5 Streaming, Debouncing & Equilibrium Break
* Events arrive continuously over Apache Kafka topics (`air.fleet`, `air.crew`, `air.payload`, `air.weather`, `air.threats`).
* **Debouncing:** The Python engine aggregates incoming events using a 1-second sliding batch window to prevent solver thrashing.
* **Equilibrium Break Triggers:** An equilibrium break is declared when an incoming event invalidates an active flight assignment:
  1. An assigned airframe reports an unscheduled mechanical fault.
  2. A destination runway or departure base closes due to severe weather.
  3. An active corridor threat level exceeds the mission's risk tolerance threshold.
  4. An assigned crew member's duty limit is breached.
* Upon declaring an equilibrium break, the Coordinator flags affected missions and initiates immediate peer renegotiation and replanning.

---

## 3. Service Boundaries & Directory Structure

```
SIH2k26_PS26250_ingestion/
├── docker-compose.yml              # Kafka broker, Zookeeper, PostgreSQL, optional Ollama
├── package.json                    # Root scripts delegating commands
│
├── services/
│   ├── ingestion/                  # SERVICE 1: Node.js / Express Ingestion Gateway
│   │   ├── src/
│   │   │   ├── api/                # REST endpoints (/events/aircraft, /crew, /payload, /weather, /threats)
│   │   │   ├── middleware/         # Auth, validation, rate limiting, error handlers
│   │   │   ├── contracts/          # Strict event schemas & validators
│   │   │   ├── transport/          # Kafka producer with transactional outbox
│   │   │   └── server.js           # Express app lifecycle
│   │   └── package.json
│   │
│   ├── agent_engine/               # SERVICE 2: Python MAGI Multi-Agent & OR-Tools Solver
│   │   ├── src/
│   │   │   ├── agents/             # Autonomous Domain Agents (Fleet, Crew, Payload, Threat, Weather, Coordinator)
│   │   │   ├── solver/             # Google OR-Tools CP-SAT Model & Verifier
│   │   │   ├── negotiation/        # Multi-round bidding, voting, and dispute protocol
│   │   │   ├── transport/          # aiokafka consumers & event dispatchers
│   │   │   ├── storage/            # PostgreSQL models & audit repository (SQLAlchemy / asyncpg)
│   │   │   ├── llm/                # Optional Ollama SLM prompt runner & fallback templates
│   │   │   └── api/                # FastAPI server (WebSocket/SSE streaming for MAGI visualizer)
│   │   ├── tests/
│   │   ├── pyproject.toml / requirements.txt
│   │   └── Dockerfile
│   │
│   ├── simulator/                  # SERVICE 3: Operational Event Injection Simulator
│   │   ├── scenarios/              # JSON/YAML scripts (Thunderstorm, Hostile Threat, Airframe Fault)
│   │   ├── injector.py             # CLI runner sending synthetic telemetry into Ingestion API
│   │   └── requirements.txt
│   │
│   └── dashboard/                  # SERVICE 4: Operational Command & MAGI Visualizer
│       └── [FROZEN]                # Implementation paused until user supplies UI skills and styling palette
│
└── docs/
    └── superpowers/specs/2026-10-15-dynamic-air-operations-system-design.md
```

---

## 4. Multi-Objective Solver Formulation (OR-Tools CP-SAT)

The optimization engine solves a lexicographic / weighted multi-objective formulation:
$$\max \quad \left( W_{\text{priority}} \cdot \sum P_{\text{served}} - W_{\text{threat}} \cdot \sum \text{Risk}_{\text{corridor}} - W_{\text{churn}} \cdot \sum \Delta_{\text{reassign}} - W_{\text{delay}} \cdot \sum T_{\text{delay}} \right)$$

Subject to:
1. **Airframe Availability & Range:** Total route distance $\le$ aircraft maximum operational range; payload mass $\le$ maximum payload capacity.
2. **Crew Certification & Duty:** Crew qualification matches required mission profile; flight hours + turnaround $\le$ maximum allowed duty window.
3. **Runway & Base Capacity:** Number of concurrent departures/arrivals in slot $t$ at airbase $b$ $\le \text{Capacity}(b, t)$.
4. **Corridor Feasibility:** Corridor $c$ is traversable only if $\text{Weather}(c, t) \ne \text{Storm}$ and $\text{ThreatLevel}(c, t) \le \text{Threshold}$.
5. **Plan Stability (Anti-Churn):** During replanning, previously confirmed assignments are penalized if modified unless necessary to maintain feasibility.

---

## 5. Goals, Non-Goals, and Anti-Goals

### Goals
* Clean decoupling: JavaScript handles high-throughput ingestion and Kafka streaming; Python handles agent negotiation, machine learning, and Operations Research solving.
* Complete mathematical transparency: Every mission schedule is verified by OR-Tools CP-SAT.
* Autonomous MAGI-inspired consensus: Domain agents actively debate, vote, and form consensus plans.
* Realistic dynamic replanning: Disruption events from the simulator immediately break equilibrium and trigger visible adaptation.
* Full auditability: Every agent objection, proposal, and solver slack metric is persisted to PostgreSQL.

### Non-Goals
* No live kinetic weapons deployment or real-world targeting (decision-support prototype under SIH guidelines).
* No external cloud dependencies required (fully runnable via local Docker Compose).

### Anti-Goals
* No monolithic "all-in-JS" shortcut.
* No black-box LLM guessing flight assignments without mathematical proof.
* No static mock data: Everything must flow live through Kafka into the solver.

---

## 6. What is Left to the Builder

* Defining exact Pydantic event schemas for dynamic threat detections.
* Finalizing tuning constants ($W_{\text{priority}}, W_{\text{threat}}, W_{\text{churn}}, W_{\text{delay}}$) for the CP-SAT objective function.
* Implementing the WebSocket JSON schema streaming the MAGI agent thought graph to the dashboard.
