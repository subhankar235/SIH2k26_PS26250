"""Pydantic request and response models for the Air Power API.

These API contracts mirror the operational entities in ``infra/db/init.sql``.
Database persistence is intentionally separate from these transport models.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class APIModel(BaseModel):
    """Shared API model configuration."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class HealthResponse(APIModel):
    status: str
    service: str


class GridSummary(APIModel):
    total_assets: int = Field(ge=0)
    healthy_assets: int = Field(ge=0)
    active_alerts: int = Field(ge=0)
    renewable_share: float = Field(ge=0, le=1)
    demand_mw: float = Field(ge=0)
    reserve_margin: float = Field(ge=0, le=1)


class GridAssetCreate(APIModel):
    asset_id: str = Field(min_length=1, max_length=200)
    asset_type: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    region: str | None = Field(default=None, max_length=200)
    capacity_mw: float = Field(ge=0)
    status: Literal["healthy", "degraded", "offline", "maintenance", "unknown"] = "unknown"
    attributes: dict[str, Any] = Field(default_factory=dict)


class GridAssetRead(GridAssetCreate):
    created_at: datetime
    updated_at: datetime


class GridEventCreate(APIModel):
    asset_id: str | None = None
    event_type: str = Field(min_length=1, max_length=150)
    severity: Literal["info", "warning", "critical"] = "info"
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str | None = Field(default=None, max_length=200)
    observed_at: datetime | None = None


class GridEventRead(GridEventCreate):
    event_id: int
    observed_at: datetime
    received_at: datetime


class SourceRecordCreate(APIModel):
    source_name: str = Field(min_length=1, max_length=200)
    external_id: str | None = Field(default=None, max_length=300)
    record_type: str = Field(min_length=1, max_length=100)
    asset_id: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    normalized_data: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = Field(default=None, max_length=256)
    source_uri: str | None = Field(default=None, max_length=2000)
    observed_at: datetime | None = None


class SourceRecordRead(SourceRecordCreate):
    record_id: UUID
    ingested_at: datetime


class EvidenceClaimCreate(APIModel):
    record_id: UUID
    asset_id: str | None = None
    subject: str = Field(min_length=1, max_length=500)
    predicate: str = Field(min_length=1, max_length=200)
    object_value: Any
    unit: str | None = Field(default=None, max_length=100)
    confidence: float = Field(default=1.0, ge=0, le=1)
    claim_status: Literal["active", "superseded", "rejected", "uncertain"] = "active"
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def validate_validity_window(self) -> "EvidenceClaimCreate":
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be greater than or equal to valid_from")
        return self


class EvidenceClaimRead(EvidenceClaimCreate):
    claim_id: UUID
    created_at: datetime


class OperationalConstraintCreate(APIModel):
    asset_id: str | None = None
    constraint_type: str = Field(min_length=1, max_length=150)
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    source_record_id: UUID | None = None
    priority: int = Field(default=100, ge=0)
    is_hard: bool = True
    active_from: datetime | None = None
    active_until: datetime | None = None

    @model_validator(mode="after")
    def validate_active_window(self) -> "OperationalConstraintCreate":
        if self.active_from and self.active_until and self.active_until < self.active_from:
            raise ValueError("active_until must be greater than or equal to active_from")
        return self


class OperationalConstraintRead(OperationalConstraintCreate):
    constraint_id: UUID
    created_at: datetime


class ForecastCreate(APIModel):
    asset_id: str | None = None
    metric: str = Field(min_length=1, max_length=150)
    model_name: str = Field(min_length=1, max_length=200)
    model_version: str | None = Field(default=None, max_length=100)
    predicted_value: float
    lower_bound: float | None = None
    upper_bound: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    unit: str | None = Field(default=None, max_length=100)
    features: dict[str, Any] = Field(default_factory=dict)
    valid_at: datetime

    @model_validator(mode="after")
    def validate_interval(self) -> "ForecastCreate":
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("lower_bound must not exceed upper_bound")
        return self


class ForecastRead(ForecastCreate):
    forecast_id: UUID
    issued_at: datetime


class PlanCreate(APIModel):
    name: str = Field(min_length=1, max_length=300)
    objective: str = Field(default="resilience", min_length=1, max_length=150)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = Field(default=None, max_length=200)
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def validate_validity_window(self) -> "PlanCreate":
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be greater than or equal to valid_from")
        return self


class PlanActionCreate(APIModel):
    asset_id: str = Field(min_length=1, max_length=200)
    action_type: str = Field(min_length=1, max_length=150)
    parameters: dict[str, Any] = Field(default_factory=dict)
    sequence_no: int = Field(default=0, ge=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    expected_cost: float | None = Field(default=None, ge=0)
    expected_impact: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action_window(self) -> "PlanActionCreate":
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must be greater than or equal to starts_at")
        return self


class PlanActionRead(PlanActionCreate):
    action_id: UUID
    plan_id: UUID
    created_at: datetime


class PlanRead(PlanCreate):
    plan_id: UUID
    status: Literal[
        "draft",
        "validating",
        "pending_approval",
        "approved",
        "rejected",
        "active",
        "completed",
        "cancelled",
        "invalidated",
    ]
    objective_value: float | None = None
    created_at: datetime
    updated_at: datetime
    actions: list[PlanActionRead] = Field(default_factory=list)


class DecisionCreate(APIModel):
    plan_id: UUID | None = None
    decision_type: str = Field(min_length=1, max_length=150)
    rationale: str = ""
    evidence: list[Any] = Field(default_factory=list)
    assumptions: list[Any] = Field(default_factory=list)
    created_by: str | None = Field(default=None, max_length=200)


class DecisionRead(DecisionCreate):
    decision_id: UUID
    status: Literal["proposed", "valid", "invalid", "superseded", "executed"]
    validity_status: Literal["valid", "at_risk", "invalid", "unverified"]
    validity_until: datetime | None = None
    created_at: datetime


class ApprovalCreate(APIModel):
    decision_id: UUID
    requested_by: str | None = Field(default=None, max_length=200)
    comment: str = ""


class ApprovalRead(ApprovalCreate):
    approval_id: UUID
    status: Literal["pending", "approved", "rejected", "withdrawn"]
    reviewer: str | None = None
    requested_at: datetime
    resolved_at: datetime | None = None


class AgentRunCreate(APIModel):
    workflow: str = Field(min_length=1, max_length=200)
    input: dict[str, Any] = Field(default_factory=dict)
    related_decision: UUID | None = None


class AgentRunRead(AgentRunCreate):
    run_id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled", "waiting_approval"]
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class AuditLogRead(APIModel):
    audit_id: int
    actor: str
    action: str
    entity_type: str
    entity_id: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class ExperimentCreate(APIModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    model_name: str | None = Field(default=None, max_length=200)
    dataset_version: str | None = Field(default=None, max_length=200)
    configuration: dict[str, Any] = Field(default_factory=dict)


class ExperimentRead(ExperimentCreate):
    experiment_id: UUID
    created_at: datetime


class BenchmarkResultCreate(APIModel):
    experiment_id: UUID
    metric: str = Field(min_length=1, max_length=150)
    metric_value: float
    sample_count: int | None = Field(default=None, ge=0)
    artifacts: dict[str, Any] = Field(default_factory=dict)


class BenchmarkResultRead(BenchmarkResultCreate):
    result_id: UUID
    evaluated_at: datetime
