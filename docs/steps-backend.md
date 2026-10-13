# Air Power — Backend Specification (AI-Agent Ready)

This file is written so an AI coding agent can build any backend file from this document alone. Every file entry gives: **location**, **objective**, **inputs → outputs**, **structure (signatures)**, **rules**, **dependencies**, and **tests**.

All data is synthetic and non-operational.

---

## 0. How an AI Agent Should Use This File

1. Read **§1 Global Conventions** and **§2 Shared Contracts** first. They apply to every file.
2. Find the file entry (use the path as the search key).
3. Create the file at exactly that path with the listed signatures. Keep names identical (other files import them).
4. Respect **§3 Import Boundaries**. Violating them breaks the independence guarantee of verification.
5. Write the tests listed for that file in the same change.
6. Run the **Definition of Done** (§14) before finishing.

**Prompt template to give an agent**

```
Read BACKEND.md. Implement: <path>.
Follow §1 and §2. Match the signatures exactly. Write the tests listed.
Do not edit other files except to register routers/imports.
```

---

## 1. Global Conventions

| Topic | Rule |
|---|---|
| Python | 3.11+, full type hints, `from __future__ import annotations` |
| Style | `ruff` + `black` (line length 100), `mypy` on `app/` |
| Pydantic | v2 (`BaseModel`, `model_validate`, `ConfigDict(from_attributes=True)`) |
| ORM | SQLAlchemy 2.0 style (`Mapped[...]`, `mapped_column`), sync sessions |
| Time | Always timezone-aware UTC `datetime`. Store both `event_time` and `ingest_time` |
| IDs | `uuid.UUID` (uuid4). Exposed as strings in JSON |
| Seeds | Any stochastic function takes `seed: int` and uses a local `numpy.random.Generator` / seeded library RNG. Never use global RNG state |
| Versioning | Records, forecasts, schedules, decisions carry an integer `version` that only increases |
| Deletion | No hard deletes. Use `superseded_by` / flags |
| Audit | Every state change calls `audit_service.record(...)` in the same DB transaction |
| Errors | Raise subclasses of `AirPowerError`. Routers never catch generic `Exception` |
| Logging | Structured (JSON) with `correlation_id`; never log raw payloads containing full records at INFO |
| Purity | Services take a `Session` argument; no module-level globals holding state |
| Determinism | Same input + same seed → identical output |
| Docstrings | One-line summary + `Args/Returns/Raises` for public functions |

---

## 2. Shared Contracts

### 2.1 Enums — `backend/app/core/enums.py`

```python
from enum import StrEnum

class SourceType(StrEnum):
    RESOURCE = "resource"; CREW = "crew"; AVAILABILITY = "availability"
    WEATHER = "weather"; CONSTRAINT = "constraint"

class IssueClass(StrEnum):
    STALE = "stale"; MISSING = "missing"; DUPLICATE = "duplicate"; CONFLICT = "conflict"

class ValidityStatus(StrEnum):
    VERIFIED = "verified"; STALE = "stale"; INVALIDATED = "invalidated"; UNCERTAIN = "uncertain"

class VerificationOutcome(StrEnum):
    VERIFIED = "verified"; INVALID = "invalid"; UNCERTAIN = "uncertain"

class ScheduleStatus(StrEnum):
    DRAFT = "draft"; VERIFIED = "verified"; INVALID = "invalid"; UNCERTAIN = "uncertain"
    APPROVED = "approved"; REJECTED = "rejected"; SUPERSEDED = "superseded"

class ApprovalDecision(StrEnum):
    APPROVED = "approved"; REJECTED = "rejected"

class AgentRunStatus(StrEnum):
    PENDING = "pending"; RUNNING = "running"; AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"; FAILED = "failed"; ESCALATED = "escalated"

class FaultType(StrEnum):
    MISSING = "missing"; STALE = "stale"; CONFLICTING = "conflicting"
    CONSTRAINT_CHANGE = "constraint_change"
```

### 2.2 Error response (all non-2xx)

```json
{ "code": "NOT_FOUND", "message": "Decision not found", "details": {"id": "..."} }
```

| Exception | HTTP | `code` |
|---|---|---|
| `NotFoundError` | 404 | `NOT_FOUND` |
| `RequestValidationFailed` | 422 | `VALIDATION_ERROR` |
| `ConflictError` | 409 | `CONFLICT` |
| `VerificationFailed` | 422 | `VERIFICATION_FAILED` |
| `SolverInfeasible` | 422 | `INFEASIBLE` |
| `ForbiddenError` | 403 | `FORBIDDEN` |
| `AirPowerError` (base) | 500 | `INTERNAL` |

### 2.3 Pagination

Query: `?limit=50&offset=0`. Response: `{"items": [...], "total": int, "limit": int, "offset": int}`.

### 2.4 Idempotency

Create/solve endpoints accept header `Idempotency-Key`. Same key + same body → return the stored result, no new work.

---

## 3. Import Boundaries (Critical)

| Package | May import | Must NOT import |
|---|---|---|
| `app/services/verification/*` | `app.core`, `app.db`, `app.schemas`, `app.utils` | `optimisation`, `app.agents`, `ml`, `app.services.planning` |
| `app/services/audit/*` | `app.core`, `app.db` | everything else |
| `app/agents/*` | `app.services.*`, `app.schemas`, `app.core` | direct DB writes to verification/audit tables (go through services) |
| `app/api/v1/*` | `app.services.*`, `app.schemas`, `app.core.deps` | `app.db.models` directly (use services) |
| `app/services/*` | `app.db`, `app.core`, `app.schemas`, `app.utils`, `optimisation`, `ml` (inference only) | `app.api`, `app.agents` |
| `ml/*`, `optimisation/*`, `simulation/*`, `evaluation/*` | stdlib + own libs; may call `app.services` only in `evaluation/` and `simulation/runner/` | `app.api` |

Reason: the verifier must stay independent so that a bug in the solver or an agent cannot also break the check.

---

## 4. Repository Layout (Backend-Related)

```
backend/            FastAPI app, services, agents, DB, tests
streaming/          Kafka producers/consumers
ml/                 Model training + inference code
optimisation/       CP-SAT / ALNS
simulation/         SimPy twin + fault injection
evaluation/         Baselines, ablations, metrics, stats, reports
data/               Synthetic data generators and splits
infra/              Dockerfiles, SQL, Kafka scripts
scripts/            Helper shell scripts
tests/              Cross-module e2e/contract/performance tests
```

---

# PART A — `backend/`

## A1. Entry and Core

### `backend/app/main.py`
- **Objective:** Create the FastAPI app, middleware, error handlers, routers.
- **Structure:**
```python
def create_app() -> FastAPI: ...
app = create_app()
```
- **Rules:** Add `CORSMiddleware` (origins from `Settings.cors_origins`); register handler mapping `AirPowerError` → JSON error schema; add middleware that sets `correlation_id` from `X-Request-ID` or new uuid; include `api_router` at `/api/v1`.
- **Tests:** `tests/api/test_health.py` (200), error-handler test (404 shape).

### `backend/app/core/config.py`
- **Objective:** Central typed settings from environment.
- **Structure:**
```python
class Settings(BaseSettings):
    postgres_user: str; postgres_password: str; postgres_db: str
    postgres_host: str = "localhost"; postgres_port: int = 5432
    kafka_bootstrap_servers: str = "localhost:9092"
    mlflow_tracking_uri: str = "http://localhost:5000"
    random_seed: int = 42
    cors_origins: list[str] = ["http://localhost:3000"]
    freshness_thresholds: dict[str, int]      # seconds per SourceType
    max_agent_retries: int = 3
    solver_time_limit_s: int = 30
    uncertainty_threshold: float = 0.35       # relative interval width
    @property
    def database_url(self) -> str: ...
@lru_cache
def get_settings() -> Settings: ...
```
- **Used by:** everything. **Tests:** env override test.

### `backend/app/core/enums.py`
- **Objective:** Single source of truth for enums (see §2.1). No logic.

### `backend/app/core/exceptions.py`
- **Objective:** Exception hierarchy (see §2.2).
- **Structure:**
```python
class AirPowerError(Exception):
    code = "INTERNAL"; http_status = 500
    def __init__(self, message: str, details: dict | None = None): ...
class NotFoundError(AirPowerError): code="NOT_FOUND"; http_status=404
class RequestValidationFailed(AirPowerError): ...
class ConflictError(AirPowerError): ...
class VerificationFailed(AirPowerError): ...
class SolverInfeasible(AirPowerError): ...
class ForbiddenError(AirPowerError): ...
```

### `backend/app/core/logging.py`
- **Objective:** JSON logging + correlation id.
- **Structure:**
```python
correlation_id_var: ContextVar[str]
def configure_logging(level: str = "INFO") -> None: ...
def get_logger(name: str) -> logging.Logger: ...
```

### `backend/app/core/security.py`
- **Objective:** Minimal auth + roles (`viewer`, `analyst`, `approver`, `admin`).
- **Structure:**
```python
class Actor(BaseModel): id: str; role: Literal["viewer","analyst","approver","admin"]
def get_actor(x_api_key: str = Header(...)) -> Actor: ...
def require_role(*roles: str) -> Callable[..., Actor]: ...   # FastAPI dependency factory
```
- **Rules:** approvals endpoint requires `approver`; audit endpoints require `viewer+`; API keys come from env/DB table.

### `backend/app/core/deps.py`
- **Objective:** Shared FastAPI dependencies.
- **Structure:**
```python
def get_db() -> Iterator[Session]: ...        # commit on success, rollback on error
def get_idempotency_key(idempotency_key: str | None = Header(None)) -> str | None: ...
```

---

## A2. Database

### `backend/app/db/session.py`
```python
engine: Engine
SessionLocal: sessionmaker[Session]
def session_scope() -> Iterator[Session]: ...  # for scripts/consumers
```

### `backend/app/db/base.py`
- **Objective:** Declarative `Base` + mixins.
```python
class Base(DeclarativeBase): ...
class UUIDPk: id: Mapped[uuid.UUID]            # default uuid4
class CreatedAt: created_at: Mapped[datetime]  # default now(UTC)
class Versioned: version: Mapped[int]          # default 1
```

### ORM models — `backend/app/db/models/`

| File | Table(s) | Key columns |
|---|---|---|
| `source.py` | `source` | id, name (unique), source_type, reliability_prior (float) |
| `record.py` | `raw_event`, `record` | raw_event: id, source_id, source_event_id, payload (JSONB), event_time, ingest_time; unique(source_id, source_event_id). record: id, entity_id, source_type, normalised_payload (JSONB), version, source_id, raw_event_id, event_time, ingest_time, flags (JSONB list), superseded_by (nullable) |
| `claim.py` | `claim`, `issue`, `evidence_edge` | claim: id, record_id, attribute, value (JSONB), source_id, observed_at, superseded_by. issue: id, issue_class (IssueClass), claim_ids (JSONB), detected_at, status (open/resolved), details (JSONB). evidence_edge: id, from_id, to_id, relation, timestamp |
| `decision.py` | `decision`, `assumption`, `dependency` | decision: id, decision_type, version, status (ValidityStatus), created_at, ref_id. assumption: id, decision_id, description, parameters (JSONB). dependency: id, decision_id, input_type, input_id, input_version |
| `forecast.py` | `forecast` | id, target, horizon, points (JSONB: mean/lower/upper), calibration_meta (JSONB), input_versions (JSONB), version, high_uncertainty (bool) |
| `schedule.py` | `schedule` | id, version, parent_schedule_id, assignments (JSONB), objectives (JSONB), solver_meta (JSONB), status (ScheduleStatus), problem_hash |
| `experiment.py` | `experiment_run` | id, scenario, seed, config (JSONB), metrics (JSONB), mlflow_run_id, created_at |
| `agent_run.py` | `agent_run` | id, request (JSONB), graph_state (JSONB), checkpoints (JSONB), retries (int), status (AgentRunStatus), explanation (JSONB), idempotency_key |
| `approval.py` | `verification_result`, `approval` | verification_result: id, target_type, target_id, outcome, violations (JSONB), uncertainty_flags (JSONB), checked_at. approval: id, target_type, target_id, approver, decision, rationale, decided_at |
| `audit_log.py` | `audit_entry` | id, entity_type, entity_id, action, before_ref (JSONB), after_ref (JSONB), actor, correlation_id, created_at. **Append-only** |

**Rules:** add DB-level trigger (in migration) that raises on `UPDATE`/`DELETE` of `audit_entry`. Index: `record(entity_id, source_type)`, `claim(record_id)`, `dependency(input_id)`, `audit_entry(entity_type, entity_id)`.

### `backend/app/db/migrations/`
- Alembic env + versions. First migration creates all tables, indexes, and the audit append-only trigger.

---

## A3. Schemas — `backend/app/schemas/`

Pydantic v2 models for requests/responses. One file per domain; all inherit `ConfigDict(from_attributes=True)`.

| File | Key models |
|---|---|
| `common.py` | `Page[T]`, `ErrorResponse`, `IdResponse` |
| `ingestion.py` | `IngestEventIn(source, source_event_id, event_time, payload)`, `RecordOut`, `IngestStatusOut(topics: list[TopicStatus])`, `FlaggedRecordOut(record, reasons)` |
| `evidence.py` | `ClaimOut`, `IssueOut`, `AutopsyOut(issue, claims, provenance, missing_information, uncertainty)`, `ProvenanceStep` |
| `validity.py` | `DecisionOut(id, type, version, status, assumptions, dependencies)`, `ReverifyIn(change_events)`, `ReverifyOut(affected, status_changes, nodes_touched)` |
| `forecast.py` | `ForecastIn(target, horizon, seed)`, `ForecastPoint(t, mean, lower, upper)`, `ForecastOut` |
| `planning.py` | `ProblemIn(tasks, resources, windows, precedence, policies, objectives)`, `Assignment(task_id, resource_id, start, end)`, `ScheduleOut`, `SolveIn(problem, use_alns, time_limit_s, seed)`, `AlternativesOut` |
| `replanning.py` | `ReplanIn(schedule_id, changes)`, `ScheduleDiff(added, removed, moved, unchanged)`, `ReplanOut` |
| `stress.py` | `StressRunIn(scenario, seed, severity)`, `StressRunOut(id, status, metrics)` |
| `agents.py` | `AgentRequestIn`, `AgentRunOut(status, steps, retries)`, `ExplanationOut(text, evidence_refs)` |
| `verification.py` | `VerifyIn(target_type, target_id)`, `Violation(rule, message, refs)`, `VerificationOut(outcome, violations, uncertainty_flags)` |
| `approvals.py` | `ApprovalQueueItem`, `ApprovalDecisionIn(decision, rationale)` |
| `audit.py` | `AuditEntryOut`, `AuditQuery` |
| `benchmarks.py` | `BenchmarkResultOut`, `AblationOut`, `StatResult(effect_size, ci_low, ci_high, p_value)` |

**Rule:** `ExplanationOut.evidence_refs` is required and non-empty; validator rejects empty list.

---

## A4. API Routers — `backend/app/api/`

### `backend/app/api/router.py`
```python
api_router = APIRouter()
# include each v1 router with prefix and tags
```

### Routers (`backend/app/api/v1/`)

Each router is thin: parse → call one service function → return schema. No business logic.

| File | Endpoint | Method | Auth role | Service call | Response |
|---|---|---|---|---|---|
| `health.py` | `/health` | GET | none | DB ping | `{status, db}` |
| `ingestion.py` | `/ingestion/events` | POST | analyst | `ingestion.ingest_event` | 202 `RecordOut` |
| | `/ingestion/status` | GET | viewer | `ingestion.get_status` | `IngestStatusOut` |
| | `/ingestion/flagged` | GET | viewer | `ingestion.list_flagged` | `Page[FlaggedRecordOut]` |
| `evidence.py` | `/evidence/issues` | GET | viewer | `evidence.list_issues` | `Page[IssueOut]` (filter `issue_class`) |
| | `/evidence/issues/{id}/autopsy` | GET | viewer | `evidence.build_autopsy` | `AutopsyOut` |
| | `/evidence/provenance/{record_id}` | GET | viewer | `evidence.trace` | `list[ProvenanceStep]` |
| `validity.py` | `/validity/decisions` | GET | viewer | `validity.list_decisions` | `Page[DecisionOut]` (filter `status`) |
| | `/validity/decisions/{id}` | GET | viewer | `validity.get_decision` | `DecisionOut` |
| | `/validity/reverify` | POST | analyst | `validity.reverify` | `ReverifyOut` |
| `forecasts.py` | `/forecasts` | POST | analyst | `forecasting.create_forecast` | `ForecastOut` |
| | `/forecasts/{id}` | GET | viewer | `forecasting.get` | `ForecastOut` |
| `planning.py` | `/planning/solve` | POST | analyst | `planning.solve_and_verify` | `ScheduleOut` |
| | `/planning/schedules/{id}` | GET | viewer | `planning.get_schedule` | `ScheduleOut` |
| | `/planning/alternatives` | GET | viewer | `planning.list_alternatives` | `AlternativesOut` |
| `replanning.py` | `/replanning/run` | POST | analyst | `replanning.replan` | `ReplanOut` |
| | `/replanning/diff/{old}/{new}` | GET | viewer | `replanning.diff` | `ScheduleDiff` |
| `stress.py` | `/stress/runs` | POST | analyst | `stress.start_run` | 202 `StressRunOut` |
| | `/stress/runs/{id}` | GET | viewer | `stress.get_run` | `StressRunOut` |
| `agents.py` | `/agents/requests` | POST | analyst | `agents.start` | 202 `AgentRunOut` |
| | `/agents/requests/{id}` | GET | viewer | `agents.get` | `AgentRunOut` |
| | `/agents/requests/{id}/explanation` | GET | viewer | `explanation.get` | `ExplanationOut` |
| `verification.py` | `/verification/check` | POST | analyst | `verification.run_checks` | `VerificationOut` |
| | `/verification/{id}` | GET | viewer | `verification.get` | `VerificationOut` |
| `approvals.py` | `/approvals` | GET | approver | `approval_router.queue` | `Page[ApprovalQueueItem]` |
| | `/approvals/{id}/decision` | POST | approver | `approval_router.decide` | `ApprovalOut` (409 if target not verified) |
| `audit.py` | `/audit` | GET | viewer | `audit_service.query` | `Page[AuditEntryOut]` |
| | `/audit/{entity}/{id}` | GET | viewer | `audit_service.history` | `list[AuditEntryOut]` |
| `benchmarks.py` | `/benchmarks/results` | GET | viewer | `benchmarking.results` | `list[BenchmarkResultOut]` |
| | `/benchmarks/ablations` | GET | viewer | `benchmarking.ablations` | `list[AblationOut]` |

**Rules:** No `PUT`/`PATCH`/`DELETE` on `/audit`. Long-running calls (`stress`, `agents`) return `202` and are polled.

---

## A5. Services — `backend/app/services/`

### A5.1 Ingestion (F1) — `services/ingestion/`

#### `validator.py`
- **Objective:** Validate incoming events against per-source Pydantic schemas.
- **Structure:**
```python
class ValidationResult(BaseModel): ok: bool; errors: list[str]; model: BaseModel | None
SCHEMAS: dict[SourceType, type[BaseModel]]
def validate_event(source: SourceType, payload: dict) -> ValidationResult: ...
```
- **Rules:** never raises on bad data; returns `ok=False` with messages. **Tests:** valid/invalid/missing-field per source.

#### `normaliser.py`
- **Objective:** Convert units, formats, ids, timestamps to canonical form.
- **Structure:**
```python
def normalise(source: SourceType, model: BaseModel, ingest_time: datetime) -> NormalisedRecord: ...
def to_utc(ts: str | datetime) -> datetime: ...
def canonical_entity_id(source: SourceType, raw_id: str) -> str: ...
```
- **Rules:** keep both `event_time` and `ingest_time`; unknown fields preserved in `extras`.

#### `deduplicator.py`
- **Objective:** Detect exact and near duplicates.
- **Structure:**
```python
def dedupe_key(rec: NormalisedRecord) -> str: ...                 # deterministic hash
def find_duplicate(db: Session, rec: NormalisedRecord) -> Record | None: ...
def classify(db: Session, rec: NormalisedRecord) -> DedupeDecision: ...  # NEW | EXACT_DUP | AMBIGUOUS
```
- **Rules:** deterministic key first; `AMBIGUOUS` goes to `entity_matcher`.

#### `entity_matcher.py`
- **Objective:** Resolve ambiguous matches with Ditto.
- **Structure:**
```python
class MatchResult(BaseModel): is_match: bool; probability: float; flagged: bool
def match(a: NormalisedRecord, b: Record, threshold: float = 0.9, low: float = 0.5) -> MatchResult: ...
```
- **Rules:** if `low <= p < threshold` → `flagged=True`, do not merge. If Ditto model missing, fall back to rule-based similarity. **Calls:** `ml.entity_matching.infer`.

#### `ingestion_service.py` (orchestrator)
```python
def ingest_event(db: Session, source: SourceType, source_event_id: str,
                 event_time: datetime, payload: dict) -> Record: ...
def get_status(db: Session) -> IngestStatusOut: ...
def list_flagged(db: Session, limit: int, offset: int) -> Page[FlaggedRecordOut]: ...
```
- **Flow:** store `raw_event` (idempotent on `(source_id, source_event_id)`) → validate → normalise → classify → store `record` or flag → audit.
- **Rules:** invalid events still stored with `flags=["invalid"]` + reasons; never dropped.

---

### A5.2 Evidence (F2 · USP 1) — `services/evidence/`

#### `staleness_checker.py`
```python
def is_stale(rec: Record, now: datetime, thresholds: dict[SourceType, int]) -> bool: ...
def find_stale(db: Session, now: datetime) -> list[Issue]: ...
```

#### `contradiction_detector.py`
```python
def find_conflicts(db: Session, entity_id: str, attribute: str | None = None) -> list[Issue]: ...
def find_duplicates(db: Session) -> list[Issue]: ...
def find_missing(db: Session, required: dict[SourceType, list[str]]) -> list[Issue]: ...
def detect_all(db: Session, now: datetime) -> list[Issue]: ...
```
- **Rules:** a conflict = same entity+attribute, different values, overlapping validity windows, ≥2 sources.

#### `evidence_graph.py`
```python
def build_graph(db: Session, entity_ids: list[str] | None = None) -> nx.MultiDiGraph: ...
# nodes: claim, source, entity, record; edges: asserted_by, about, supersedes, derived_from (with timestamp)
def neighbours(g: nx.MultiDiGraph, node_id: str, depth: int = 2) -> nx.MultiDiGraph: ...
```

#### `provenance_tracer.py`
```python
def trace(db: Session, record_id: UUID) -> list[ProvenanceStep]: ...   # origin → transformations → versions
def version_chain(db: Session, record_id: UUID) -> list[Record]: ...
```

#### `uncertainty.py`
- **Objective:** Per-claim and per-source reliability with uncertainty.
```python
def source_reliability(db: Session, seed: int) -> dict[UUID, ReliabilityEstimate]: ...  # mean, hdi_low, hdi_high
def claim_belief(issue: Issue, reliabilities: dict) -> list[ClaimBelief]: ...
```
- **Calls:** `ml.bayesian`. Fallback: Beta-Binomial closed form if PyMC unavailable.

#### `autopsy.py`
```python
def build_autopsy(db: Session, issue_id: UUID) -> AutopsyOut: ...
def missing_information(issue: Issue, g: nx.MultiDiGraph) -> list[str]: ...
```
- **Output must contain:** competing claims (value, source, observed_at), provenance timeline, missing-information list, uncertainty values.

---

### A5.3 Validity (F3 · USP 2) — `services/validity/`

#### `dependency_graph.py`
```python
def build(db: Session) -> nx.DiGraph: ...             # input(version) → assumption → decision
def affected_decisions(g: nx.DiGraph, changed_inputs: list[InputRef]) -> set[UUID]: ...
def descendants_only(g: nx.DiGraph, node: str) -> set[str]: ...
```

#### `assumption_tracker.py`
```python
def register_decision(db: Session, decision_type: str, ref_id: UUID,
                      inputs: list[InputRef], assumptions: list[AssumptionIn]) -> Decision: ...
def envelope(db: Session, decision_id: UUID) -> ValidityEnvelope: ...
```

#### `change_detector.py`
```python
def detect_changes(series: dict[str, np.ndarray], hazard: float = 1/250, seed: int = 0) -> list[ChangePoint]: ...
def changed_inputs_since(db: Session, since: datetime) -> list[InputRef]: ...
```
- **Calls:** `ml.change_point.bocpd`.

#### `status.py`
```python
def transition(db: Session, decision: Decision, new: ValidityStatus, reason: str, actor: str) -> Decision: ...
def evaluate(decision: Decision, check_results: list[CheckResult]) -> ValidityStatus: ...
```
- **Rules:** every `transition` writes an audit entry. Allowed: any → stale/uncertain; stale → verified/invalidated; invalidated → none except new version.

#### `reverifier.py`
```python
def reverify(db: Session, change_events: list[ChangeEvent]) -> ReverifyOut: ...        # incremental
def reverify_full(db: Session) -> ReverifyOut: ...                                       # for equivalence tests
```
- **Rules:** results of `reverify` must equal `reverify_full` on statuses; record `nodes_touched`.

---

### A5.4 Forecasting (F4) — `services/forecasting/`

#### `features.py`
```python
def build_features(df: pd.DataFrame, target: str, lags: list[int], windows: list[int]) -> pd.DataFrame: ...
```
- **Rules:** no leakage (only past values); calendar + weather features optional.

#### `predictor.py`
```python
def create_forecast(db: Session, target: str, horizon: int, seed: int, model: str = "ds_dgp") -> Forecast: ...
def load_model(name: str) -> ForecastModel: ...    # Protocol: predict(X) -> (mean, lower, upper)
```
- **Rules:** store `input_versions`; fallback chain `ds_dgp → sparse_gp → arima`.

#### `calibration.py`
```python
def coverage(y: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float: ...
def ece(y, mean, std, bins: int = 10) -> float: ...
def nll(y, mean, std) -> float: ...
def flag_high_uncertainty(f: Forecast, threshold: float) -> bool: ...
```

---

### A5.5 Planning (F5) — `services/planning/`

#### `problem_builder.py`
```python
def build_problem(db: Session, req: ProblemIn, forecast_id: UUID | None = None) -> Problem: ...
def problem_hash(p: Problem) -> str: ...
```
- **Rules:** forecast uncertainty may widen durations/buffers; excluded records with open `invalid` flags unless explicitly allowed.

#### `solver_service.py`
```python
def solve_and_verify(db: Session, req: SolveIn, actor: str) -> Schedule: ...
```
- **Flow:** build problem → `optimisation.cpsat.solver.solve` → optional `alns.runner.improve` → persist schedule (status `draft`) → call `verification.run_checks` → set status → register decision (F3) → audit.
- **Raises:** `SolverInfeasible` with reason.

#### `comparator.py`
```python
def compare(schedules: list[Schedule]) -> AlternativesOut: ...   # objective table + Pareto flags
```

---

### A5.6 Replanning (F6) — `services/replanning/`

#### `diff_inputs.py`
```python
def diff_inputs(old: dict[str, InputRef], new: dict[str, InputRef]) -> list[ChangeEvent]: ...
```

#### `impact_analysis.py`
```python
def impacted_assignments(schedule: Schedule, changes: list[ChangeEvent], g: nx.DiGraph) -> ImpactSet: ...
```

#### `incremental_recompute.py`
```python
def replan(db: Session, schedule_id: UUID, changes: list[ChangeEvent], actor: str) -> ReplanOut: ...
```
- **Flow:** impact → try warm-start partial re-solve → verify → if infeasible/invalid, full re-solve → diff → persist new version (`parent_schedule_id`) → mark old `superseded` only after new is verified → audit.

#### `schedule_diff.py`
```python
def diff(old: Schedule, new: Schedule) -> ScheduleDiff: ...   # added, removed, moved(before/after), unchanged count
def stability(d: ScheduleDiff) -> float: ...                    # fraction unchanged
```

---

### A5.7 Stress (F7 API-side) — `services/stress/run_manager.py`
```python
def start_run(db: Session, req: StressRunIn, actor: str) -> ExperimentRun: ...   # enqueues; returns immediately
def get_run(db: Session, run_id: UUID) -> ExperimentRun: ...
def execute_run(run_id: UUID) -> None: ...                                         # background task, calls simulation.runner
```

---

### A5.8 Explanation (F8) — `services/explanation/explainer.py`
```python
def build_explanation(db: Session, run: AgentRun) -> ExplanationOut: ...
def validate_citations(db: Session, text: str, refs: list[EvidenceRef]) -> list[str]: ...  # returns unresolved refs
```
- **Rules:** every claim sentence must map to ≥1 `EvidenceRef(kind, id, version)` that resolves in DB; unresolved → raise `VerificationFailed`.

---

### A5.9 Verification (F9) — `services/verification/` (INDEPENDENT)

#### `constraint_checker.py`
```python
def check_capacity(schedule: ScheduleData, problem: ProblemData) -> list[Violation]: ...
def check_time_windows(...) -> list[Violation]: ...
def check_precedence(...) -> list[Violation]: ...
def check_policies(...) -> list[Violation]: ...
def check_all(schedule: ScheduleData, problem: ProblemData) -> list[Violation]: ...
```
- **Rules:** re-implements checks from scratch with plain Python; imports nothing from solver code. Operates on plain dataclasses/dicts.

#### `consistency_checker.py`
```python
def check_versions(db: Session, schedule: Schedule) -> list[Violation]: ...    # inputs still current?
def check_forecast_link(db: Session, schedule: Schedule) -> list[Violation]: ...
def check_evidence_links(db: Session, schedule: Schedule) -> list[Violation]: ...
```

#### `uncertainty_flagger.py`
```python
def flags(db: Session, schedule: Schedule, threshold: float) -> list[UncertaintyFlag]: ...
# flags: HIGH_FORECAST_UNCERTAINTY, UNRESOLVED_CONFLICT, DECISION_UNCERTAIN, STALE_INPUT
```

#### `verification_service.py`
```python
def run_checks(db: Session, target_type: str, target_id: UUID, actor: str) -> VerificationResult: ...
# outcome = INVALID if violations; else UNCERTAIN if flags; else VERIFIED
def get(db: Session, id: UUID) -> VerificationResult: ...
```

#### `approval_router.py`
```python
def route(db: Session, result: VerificationResult) -> ApprovalQueueItem | None: ...   # VERIFIED/UNCERTAIN → human queue
def queue(db: Session, limit: int, offset: int) -> Page[ApprovalQueueItem]: ...
def decide(db: Session, approval_id: UUID, decision: ApprovalDecision,
           rationale: str, actor: Actor) -> Approval: ...
```
- **Rules:** `decide(APPROVED)` raises `ConflictError` unless latest verification outcome is `VERIFIED`; rationale required (≥10 chars); writes audit.

---

### A5.10 Audit (F9) — `services/audit/audit_service.py`
```python
def record(db: Session, entity_type: str, entity_id: UUID, action: str,
           before: dict | None, after: dict | None, actor: str) -> AuditEntry: ...
def query(db: Session, filters: AuditQuery, limit: int, offset: int) -> Page[AuditEntry]: ...
def history(db: Session, entity_type: str, entity_id: UUID) -> list[AuditEntry]: ...
```
- **Rules:** no update/delete functions exist. `before/after` are references or small diffs, not full payloads.

### A5.11 Benchmarking — `services/benchmarking/results_service.py`
```python
def results(db: Session, filters: dict) -> list[BenchmarkResultOut]: ...   # reads MLflow + experiment_run
def ablations(db: Session) -> list[AblationOut]: ...
```

---

## A6. Agents (F8) — `backend/app/agents/`

#### `state.py`
```python
class AgentState(BaseModel):
    run_id: UUID
    request: AgentRequestIn
    evidence: EvidenceSummary | None = None
    forecast_ids: list[UUID] = []
    changes: list[ChangeEvent] = []
    schedule_id: UUID | None = None
    verification: VerificationOutcome | None = None
    retries: int = 0
    explanation: ExplanationOut | None = None
    status: AgentRunStatus = AgentRunStatus.PENDING
```

#### `graph.py`
```python
def build_graph(checkpointer) -> CompiledGraph: ...
# nodes: evidence → prediction → change_analysis → optimise → verify → (route) → explain → human_approval → finish
def start(db: Session, req: AgentRequestIn, actor: str) -> AgentRun: ...
def resume(db: Session, run_id: UUID, approval: ApprovalDecision) -> AgentRun: ...
```

#### `routing.py`
```python
def route_after_verify(state: AgentState) -> Literal["reanalyse","explain","escalate"]: ...
# INVALID/UNCERTAIN & retries < max → reanalyse; retries >= max → escalate; VERIFIED → explain
```

#### `retry.py`
```python
def next_attempt(state: AgentState, max_retries: int) -> AgentState: ...
def changed_since_last(state: AgentState, prev_fingerprint: str) -> bool: ...   # identical retries disallowed
```

#### `checkpointing.py`
```python
def get_checkpointer(db_url: str): ...   # Postgres saver
```

#### `human_approval.py`
```python
def approval_interrupt(state: AgentState) -> AgentState: ...   # sets status AWAITING_APPROVAL and interrupts
```

#### `nodes/` (each takes and returns `AgentState`; calls services only)
| File | Function | Calls |
|---|---|---|
| `evidence_agent.py` | `run(state, db)` | `evidence.detect_all`, `evidence.build_autopsy` |
| `prediction_agent.py` | `run(state, db)` | `forecasting.create_forecast` |
| `change_analysis_agent.py` | `run(state, db)` | `replanning.diff_inputs`, `validity.reverify` |
| `optimisation_node.py` | `run(state, db)` | `planning.solve_and_verify` or `replanning.replan` |
| `verification_node.py` | `run(state, db)` | `verification.run_checks` (**authoritative**, output cannot be edited) |
| `explanation_agent.py` | `run(state, db)` | `explanation.build_explanation` |

#### `prompts/` — `evidence.md`, `explanation.md`, `change_analysis.md`
- Plain-text prompt templates. Must instruct: cite evidence ids, never invent ids, output JSON matching schema.

**Rules:** all LLM output parsed through Pydantic; parse failure = one retry; verification node never takes LLM output as input.

---

## A7. Utils — `backend/app/utils/`
```python
# time.py
def utcnow() -> datetime: ...
def parse_iso(s: str) -> datetime: ...
# ids.py
def new_id() -> UUID: ...
def stable_hash(obj: Any) -> str: ...        # sha256 of canonical JSON
# graph_utils.py
def to_node_link(g: nx.Graph) -> dict: ...   # for API/UI
def subgraph_by_depth(g: nx.Graph, root: str, depth: int) -> nx.Graph: ...
```

---

## A8. Backend Tests — `backend/tests/`

| File | Purpose |
|---|---|
| `conftest.py` | Postgres test container/DB, session fixture with rollback, factories for source/record/claim/schedule, `client` fixture with API key headers |
| `unit/test_validator.py` | each source: valid, missing field, wrong type |
| `unit/test_deduplicator.py` | exact dup, near dup, new |
| `unit/test_contradiction_detector.py` | conflict/missing/duplicate/stale on labelled fixtures |
| `unit/test_dependency_graph.py` | affected set correctness |
| `unit/test_reverifier.py` | **incremental == full** on random change sets |
| `unit/test_constraint_checker.py` | each violation type triggers |
| `unit/test_schedule_diff.py` | added/removed/moved |
| `unit/test_audit_append_only.py` | UPDATE/DELETE blocked at DB level |
| `integration/test_ingestion_flow.py` | replay 1k events → no dupes, invalid flagged |
| `integration/test_agent_workflow.py` | full run, retries bounded, escalation |
| `integration/test_approval_flow.py` | cannot approve non-verified |
| `api/test_*.py` | status codes, schemas, auth roles, pagination |

---

# PART B — `streaming/` (F1)

### `streaming/config/topics.yaml`
- Topics: `resource`, `crew`, `availability`, `weather`, `constraint`, `dead_letter`. Fields: `partitions`, `replication`, `retention_ms`.

### `streaming/config/schemas/*.json`
- JSON Schema per source mirroring the Pydantic models in `services/ingestion/validator.py`.

### `streaming/utils/kafka_client.py`
```python
def make_producer(bootstrap: str, **cfg) -> Producer: ...
def make_consumer(bootstrap: str, group_id: str, topics: list[str], **cfg) -> Consumer: ...
```

### `streaming/utils/serialization.py`
```python
def encode(event: dict) -> bytes: ...
def decode(raw: bytes) -> dict: ...
```

### `streaming/producers/base_producer.py`
```python
class BaseProducer:
    def __init__(self, topic: str, bootstrap: str): ...
    def send(self, key: str, event: dict) -> None: ...
    def flush(self) -> None: ...
```

### `streaming/producers/synthetic_producer.py`
```python
class SyntheticProducer(BaseProducer):
    def replay(self, path: Path, rate_per_s: float, seed: int, shuffle_late: float = 0.0) -> int: ...
```
- **Objective:** replay generated data; optionally delay/duplicate a fraction (for realism).

### `streaming/producers/run_producer.py`
- CLI: `--topic --path --rate --seed`.

### `streaming/consumers/base_consumer.py`
```python
class BaseConsumer:
    def poll_loop(self, handler: Callable[[dict], None], stop: Event) -> None: ...
    def commit(self) -> None: ...
```
- **Rules:** at-least-once; commit only after DB commit; handler idempotent.

### `streaming/consumers/ingestion_consumer.py`
```python
def handle(event: dict) -> None: ...   # opens session_scope(), calls ingestion_service.ingest_event
```
- **Rules:** on unexpected error send to `dead_letter` with error + original payload.

### `streaming/consumers/dead_letter_consumer.py`
```python
def handle(event: dict) -> None: ...   # stores flagged record with reason, never drops
```

### `streaming/consumers/run_consumer.py`
- CLI entry; graceful shutdown on SIGTERM.

### Tests — `streaming/tests/`
- `test_producer.py` (serialises, keys), `test_consumer.py` (idempotent replay, dead-letter path).

---

# PART C — `ml/`

### `ml/common/seed.py`
```python
def set_all_seeds(seed: int) -> None: ...      # random, numpy, torch, cuda
```

### `ml/common/mlflow_utils.py`
```python
def start_run(experiment: str, params: dict, tags: dict | None = None) -> ContextManager: ...
def log_metrics(metrics: dict[str, float], step: int | None = None) -> None: ...
def log_artifact_path(path: Path) -> None: ...
```

### `ml/entity_matching/ditto_model.py`
```python
class DittoMatcher(nn.Module):
    def __init__(self, base: str = "distilbert-base-uncased"): ...
    def forward(self, input_ids, attention_mask) -> Tensor: ...    # logits [match, no_match]
def serialize_pair(a: dict, b: dict) -> str: ...                    # "[COL] k [VAL] v ... [SEP] ..."
```

### `ml/entity_matching/train.py`
- CLI: `--config --seed`. Loads pairs CSV, trains, logs P/R/F1 to MLflow, saves to `ml/artifacts/ditto/`.
```python
def train(cfg: DittoConfig, seed: int) -> Path: ...
```

### `ml/entity_matching/infer.py`
```python
def load(path: Path) -> DittoMatcher: ...
def predict_proba(model, a: dict, b: dict) -> float: ...
```

### `ml/temporal_graph/dataset.py`
```python
def build_temporal_graph(db_url: str, split: Literal["train","val","test"]) -> TemporalData: ...
```
- **Rules:** time-based split; features: source id embedding, attribute, value hash, time delta.

### `ml/temporal_graph/tgn/model.py`, `tgn/train.py`
```python
class TGNModel(nn.Module): ...      # memory + message + embedding + link/node classifier
def train(cfg, seed) -> Path: ...
```

### `ml/temporal_graph/strgnn/model.py`, `strgnn/train.py`
```python
class StrGNNModel(nn.Module): ...   # structural snapshot GNN for anomaly/edge-state classification
def train(cfg, seed) -> Path: ...
```

### `ml/temporal_graph/evaluate.py`
```python
def evaluate_all(split: str = "test") -> pd.DataFrame: ...   # TGN, StrGNN, rule-based, statistical: P/R/F1/AUROC
```
- **Rule:** adoption gate: model is adopted only if it beats rule-based baseline on F1 with CI excluding 0.

### `ml/bayesian/source_reliability.py`
```python
def fit(observations: pd.DataFrame, seed: int, draws: int = 1000, tune: int = 1000) -> az.InferenceData: ...
```
### `ml/bayesian/claim_posterior.py`
```python
def posterior_for_claims(idata: az.InferenceData, claims: list[ClaimObs]) -> list[ClaimPosterior]: ...
```
### `ml/bayesian/diagnostics.py`
```python
def check(idata) -> DiagnosticsReport: ...    # r_hat < 1.01, ESS, divergences
```

### `ml/change_point/hazard.py`, `bocpd.py`
```python
def constant_hazard(lam: float) -> Callable[[np.ndarray], np.ndarray]: ...
def bocpd(x: np.ndarray, hazard, mu0=0., kappa0=1., alpha0=1., beta0=1.) -> np.ndarray: ...  # run-length posterior
def change_points(R: np.ndarray, threshold: float = 0.5) -> list[int]: ...
```

### `ml/forecasting/ds_dgp/model.py`, `train.py`
```python
class DSDGP(gpytorch.models.deep_gps.DeepGP): ...   # 2–3 layers, inducing points, doubly stochastic VI
def train(cfg, seed) -> Path: ...
def predict(model, X) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...  # mean, lower, upper
```

### `ml/forecasting/baselines/{arima,lstm,sparse_gp}.py`
```python
def fit_predict(train: pd.DataFrame, test: pd.DataFrame, seed: int) -> ForecastResult: ...  # mean, lower, upper
```

### `ml/forecasting/calibration.py`
- Same metrics as `services/forecasting/calibration.py` (shared implementation imported by service).

### `ml/*/configs/*.yaml`
- Keys: `seed`, `data_path`, `epochs`, `lr`, `batch_size`, `output_dir`, model-specific.

### Notebooks — `ml/notebooks/` (exploration only; never imported by code).

---

# PART D — `optimisation/` (F5, F6)

### `optimisation/models/problem.py`
```python
@dataclass(frozen=True)
class Task: id: str; duration: int; resource_type: str; earliest: int; latest: int; priority: int = 1
@dataclass(frozen=True)
class Resource: id: str; type: str; capacity: int; available: list[tuple[int, int]]
@dataclass(frozen=True)
class Precedence: before: str; after: str; min_gap: int = 0
@dataclass(frozen=True)
class Policy: name: str; params: dict
@dataclass
class Problem:
    tasks: list[Task]; resources: list[Resource]; precedence: list[Precedence]
    policies: list[Policy]; horizon: int; objectives: dict[str, float]  # weights
```
### `optimisation/models/solution.py`
```python
@dataclass
class Assignment: task_id: str; resource_id: str; start: int; end: int
@dataclass
class Solution:
    assignments: list[Assignment]; objectives: dict[str, float]
    status: Literal["OPTIMAL","FEASIBLE","INFEASIBLE","UNKNOWN"]; wall_time_s: float; seed: int
```

### `optimisation/cpsat/model_builder.py`
```python
def build(problem: Problem) -> tuple[cp_model.CpModel, ModelVars]: ...
```
### `optimisation/cpsat/constraints/`
| File | Function |
|---|---|
| `resource_capacity.py` | `add(model, vars, problem)` — interval vars + `AddCumulative` / no-overlap per resource |
| `time_windows.py` | `add(...)` — earliest/latest + resource availability windows |
| `precedence.py` | `add(...)` — `start[after] >= end[before] + gap` |
| `policy.py` | `add(...)` — registry: `max_consecutive_hours`, `rest_gap`, `forbidden_pairs` |

### `optimisation/cpsat/objectives.py`
```python
def add_objective(model, vars, problem) -> None: ...   # weighted: makespan, cost, lateness, robustness
```
### `optimisation/cpsat/solver.py`
```python
def solve(problem: Problem, time_limit_s: int, seed: int, hint: Solution | None = None) -> Solution: ...
```
- **Rules:** set `random_seed`, `num_workers`, `max_time_in_seconds`; return `INFEASIBLE` instead of raising.

### `optimisation/alns/destroy_operators.py`, `repair_operators.py`
```python
def random_removal(state: SolutionState, rng, degree: float) -> SolutionState: ...
def resource_removal(...), time_window_removal(...), related_removal(...)
def greedy_repair(state, rng) -> SolutionState: ...
def cpsat_repair(state, rng, time_limit_s: int) -> SolutionState: ...
```
### `optimisation/alns/hybrid.py`, `runner.py`
```python
def improve(problem: Problem, initial: Solution, iterations: int, time_limit_s: int, seed: int) -> Solution: ...
```
- **Rule:** never return a solution worse than `initial`; every returned solution passes internal feasibility check (the independent verifier still runs later).

### `optimisation/incremental/warm_start.py`, `partial_resolve.py`
```python
def to_hint(prev: Solution, frozen: set[str]) -> Solution: ...
def partial_resolve(problem: Problem, prev: Solution, affected: set[str], time_limit_s: int, seed: int,
                    stability_weight: float = 0.1) -> Solution: ...   # penalises moving unaffected tasks
```

### `optimisation/benchmarks/instances/` — generated JSON instances: `small_*`, `medium_*`, `large_*`.

### Tests — `optimisation/tests/`: `test_cpsat.py`, `test_alns.py`, `test_feasibility.py` (property: returned solutions satisfy independent checker).

---

# PART E — `simulation/` (F7 · USP 3)

### `simulation/twin/clock.py`
```python
class SimClock: def now(self) -> int; def advance(self, dt: int) -> None
```
### `simulation/twin/entities.py`
```python
@dataclass class SimResource: ...; @dataclass class SimCrew: ...; @dataclass class SimTask: ...
```
### `simulation/twin/environment.py`
```python
class TwinEnvironment:
    def __init__(self, scenario: Scenario, seed: int): ...
    def run(self, until: int) -> Iterator[TwinEvent]: ...   # yields timestamped events
```

### `simulation/faults/`
| File | Function |
|---|---|
| `missing_data.py` | `apply(events, rate, fields, rng) -> (events, labels)` |
| `stale_data.py` | `apply(events, rate, lag_s, rng) -> (events, labels)` |
| `conflicting_data.py` | `apply(events, rate, delta, rng) -> (events, labels)` |
| `constraint_change.py` | `apply(problem, changes, at_time) -> (Problem, labels)` |
| `injector.py` | `inject(events, plan: FaultPlan, seed) -> InjectionResult` (`events`, `labels` ground truth) |

### `simulation/scenarios/`
- `library/*.yaml` (`baseline_clean`, `heavy_staleness`, `source_conflict`, `cascading_changes`).
- `loader.py`: `load(name) -> Scenario`.
- `generator.py`: `generate_variants(base: Scenario, strategy) -> list[Scenario]` (Hypothesis strategies).

### `simulation/runner/`
```python
# run_scenario.py
def run(scenario: Scenario, seed: int, system: SystemUnderTest) -> RunResult: ...
# metrics.py
def compute(result: RunResult, labels: GroundTruth) -> dict[str, float]:
    # detection_precision, detection_recall, false_alarm_rate, feasibility_rate, failure_rate, recovery_time
# mlflow_logger.py
def log_run(result: RunResult, metrics: dict, seed: int, scenario: str) -> str: ...
```
- `SystemUnderTest` protocol: `ingest(events)`, `detect()`, `plan()`, `verify()` — implemented by the full system and each baseline.

### `simulation/properties/`
- `test_invariants.py`: Hypothesis — random fault plans never crash the pipeline.
- `test_no_invalid_accept.py`: no `INVALID` result becomes `APPROVED`.
- `test_reproducibility.py`: same seed → identical metrics.

---

# PART F — `evaluation/` (F10)

### `evaluation/baselines/`
| File | Class |
|---|---|
| `naive_pipeline.py` | `NaiveSystem(SystemUnderTest)` — no evidence tracking, no revalidation |
| `rule_based_only.py` | `RuleBasedSystem` — thresholds only |
| `full_recompute.py` | `FullRecomputeSystem` — recompute everything on any change |

### `evaluation/ablations/`
- One class per disabled component: `NoEvidence`, `NoValidity`, `NoUncertainty`, `NoALNS`, `NoVerification`. Each wraps the full system with one flag off.

### `evaluation/metrics/`
```python
# latency.py:       summarise(times: list[float]) -> dict
# feasibility.py:   rate(results) -> float
# error_detection.py: precision_recall(pred_labels, true_labels) -> dict
# false_alarms.py:  rate(flags, clean_mask) -> float
# recovery.py:      time_to_recover(events) -> float
# calibration.py:   coverage/ece/nll (reuse ml.forecasting.calibration)
```

### `evaluation/stats/`
```python
# significance.py
def paired_test(a: np.ndarray, b: np.ndarray, method: Literal["wilcoxon","ttest"]) -> StatResult: ...
def bootstrap_ci(x: np.ndarray, stat=np.mean, n: int = 10_000, seed: int = 0) -> tuple[float, float]: ...
# effect_size.py
def cohens_d(a, b) -> float: ...
def cliffs_delta(a, b) -> float: ...
```

### `evaluation/experiments/`
- `exp_evidence_detection.py`, `exp_incremental_vs_full.py`, `exp_forecast_calibration.py`, `exp_hybrid_solver.py`, `exp_stress_end_to_end.py`.
- Each exposes `run(seeds: list[int], out_dir: Path) -> pd.DataFrame` and logs to MLflow.

### `evaluation/reports/generate_report.py`
```python
def generate(mlflow_experiment: str, out_dir: Path) -> Path: ...   # tables (CSV/MD) + figures (PNG)
```

### `evaluation/mlflow/mlflow_config.py`
- Experiment names, tag conventions (`git_sha`, `seed`, `scenario`).

---

# PART G — `data/`

### `data/generators/`
```python
# generate_resources.py:    generate(n: int, seed: int) -> pd.DataFrame
# generate_crew.py:         generate(n: int, seed: int) -> pd.DataFrame
# generate_availability.py: generate(resources, crew, horizon_days, seed) -> pd.DataFrame
# generate_weather.py:      generate(horizon_days, seed) -> pd.DataFrame
# generate_constraints.py:  generate(resources, seed) -> list[dict]
# generate_all.py:          main(seed: int, size: int, out: Path)   # writes raw/ + labels.parquet
# make_splits.py:           main(seed: int)    # time-based train/val/test for pairs, graph, forecast
```
- **Labels file schema (`labels.parquet`):** `record_id, fault_type, true_value, duplicate_of, conflict_group_id, true_freshness_time`.
- **Rules:** all generators deterministic by seed; never contain real data.

### `data/schemas/data_dictionary.md` — field-level definitions per source.

---

# PART H — Infra & Scripts (Backend-Related)

| Path | Objective |
|---|---|
| `infra/postgres/init.sql` | Create extensions (`pgcrypto`), roles, schema |
| `infra/kafka/create_topics.sh` | Create topics from `streaming/config/topics.yaml` |
| `infra/docker/backend.Dockerfile` | Python 3.11 slim, install deps, run `uvicorn app.main:app` |
| `infra/docker/streaming.Dockerfile` | Run consumer entry |
| `infra/docker/simulation.Dockerfile` | Run stress runner |
| `scripts/seed_db.sh` | Run migrations + seed sources + API keys |
| `scripts/generate_synthetic_data.sh` | `python data/generators/generate_all.py` |
| `scripts/run_benchmarks.sh` | Run all experiments + report |
| `scripts/wait_for_services.sh` | Wait for Postgres/Kafka health |

---

# PART I — Cross-Module Tests — `tests/`

| File | Verifies |
|---|---|
| `e2e/test_full_pipeline.py` | Kafka → DB → evidence → plan → verify → approve → audit |
| `e2e/test_replan_on_change.py` | Inject change → impacted decisions flagged → new verified schedule + diff |
| `e2e/test_human_approval_gate.py` | Non-verified results cannot be approved via API or agent |
| `contract/test_frontend_backend_schemas.py` | TS types match Pydantic JSON schema |
| `performance/test_latency_budget.py` | Read p95 < 500 ms; ingestion ≥ 1,000 events/s (dev machine) |

---

## 13. Build Order (Per-File Agent Tasks)

| # | Task | Files |
|---|---|---|
| 1 | Core + DB | `core/*`, `db/*`, migrations, `main.py`, `health.py` |
| 2 | Data | `data/generators/*`, `make_splits.py` |
| 3 | Ingestion | `services/ingestion/*`, `streaming/*`, ingestion router |
| 4 | Verification + audit | `services/verification/*`, `services/audit/*`, routers |
| 5 | Planning | `optimisation/models,cpsat`, `services/planning/*`, router; then `alns/` |
| 6 | Evidence | `services/evidence/*`, `ml/bayesian/*`, router; then `ml/entity_matching`, `ml/temporal_graph` |
| 7 | Validity | `services/validity/*`, `ml/change_point/*`, router |
| 8 | Forecasting | `ml/forecasting/baselines` → `ds_dgp`; `services/forecasting/*`, router |
| 9 | Replanning | `optimisation/incremental/*`, `services/replanning/*`, router |
| 10 | Agents | `agents/*`, `services/explanation/*`, routers |
| 11 | Stress lab | `simulation/*`, `services/stress/*`, router |
| 12 | Evaluation | `evaluation/*`, `services/benchmarking/*`, router |
| 13 | Hardening | e2e/contract/performance tests, Dockerfiles |

---

## 14. Definition of Done (Per File / Task)

- [ ] File exists at the listed path with the listed signatures.
- [ ] Type hints complete; `mypy app/` passes.
- [ ] `ruff` + `black --check` pass.
- [ ] Listed tests written and passing.
- [ ] Respects §3 import boundaries.
- [ ] Seeds and versions handled per §1.
- [ ] State changes write audit entries.
- [ ] Errors use `AirPowerError` subclasses.
- [ ] Public functions have docstrings.

---

## 15. Non-Negotiable Rules (Summary)

1. The verifier is independent and authoritative; agents and models are advisory.
2. Never drop bad data. Store it and flag it.
3. Audit is append-only, enforced at the database level.
4. Incremental results must equal full-recompute results.
5. Everything stochastic is seeded; everything stored is versioned.
6. Advanced models are adopted only if they beat baselines.
7. Only `VERIFIED` results can be approved by a human.
