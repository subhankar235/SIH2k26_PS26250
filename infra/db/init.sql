-- Air Power operational schema (PostgreSQL 16+).
-- Applied by Docker Compose on first database initialization. For existing
-- deployments, apply equivalent versioned migrations instead.

CREATE TABLE IF NOT EXISTS grid_assets (
    asset_id         TEXT PRIMARY KEY,
    asset_type       TEXT NOT NULL,
    name             TEXT NOT NULL,
    region           TEXT,
    capacity_mw      DOUBLE PRECISION NOT NULL CHECK (capacity_mw >= 0),
    status           TEXT NOT NULL DEFAULT 'unknown'
                     CHECK (status IN ('healthy', 'degraded', 'offline', 'maintenance', 'unknown')),
    attributes       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS grid_events (
    event_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id         TEXT REFERENCES grid_assets(asset_id) ON DELETE SET NULL,
    event_type       TEXT NOT NULL,
    severity         TEXT NOT NULL DEFAULT 'info'
                     CHECK (severity IN ('info', 'warning', 'critical')),
    payload          JSONB NOT NULL DEFAULT '{}'::jsonb,
    source           TEXT,
    observed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    received_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Original and normalized source records used for provenance and deduplication.
CREATE TABLE IF NOT EXISTS source_records (
    record_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name      TEXT NOT NULL,
    external_id      TEXT,
    record_type      TEXT NOT NULL,
    asset_id         TEXT REFERENCES grid_assets(asset_id) ON DELETE SET NULL,
    raw_payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    normalized_data  JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_hash     TEXT,
    source_uri       TEXT,
    observed_at      TIMESTAMPTZ,
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_name, external_id)
);

-- Atomic, traceable statements extracted from source records.
CREATE TABLE IF NOT EXISTS evidence_claims (
    claim_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id        UUID NOT NULL REFERENCES source_records(record_id) ON DELETE CASCADE,
    asset_id         TEXT REFERENCES grid_assets(asset_id) ON DELETE SET NULL,
    subject          TEXT NOT NULL,
    predicate        TEXT NOT NULL,
    object_value     JSONB NOT NULL,
    unit             TEXT,
    confidence       DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    claim_status     TEXT NOT NULL DEFAULT 'active'
                     CHECK (claim_status IN ('active', 'superseded', 'rejected', 'uncertain')),
    valid_from       TIMESTAMPTZ,
    valid_until      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from)
);

-- Operational, safety, and planning constraints. A NULL asset_id means grid-wide.
CREATE TABLE IF NOT EXISTS operational_constraints (
    constraint_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id         TEXT REFERENCES grid_assets(asset_id) ON DELETE CASCADE,
    constraint_type  TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    parameters       JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_record_id UUID REFERENCES source_records(record_id) ON DELETE SET NULL,
    priority         INTEGER NOT NULL DEFAULT 100 CHECK (priority >= 0),
    is_hard          BOOLEAN NOT NULL DEFAULT TRUE,
    active_from      TIMESTAMPTZ,
    active_until     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (active_until IS NULL OR active_from IS NULL OR active_until >= active_from)
);

CREATE TABLE IF NOT EXISTS forecasts (
    forecast_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id         TEXT REFERENCES grid_assets(asset_id) ON DELETE CASCADE,
    metric           TEXT NOT NULL,
    model_name       TEXT NOT NULL,
    model_version    TEXT,
    predicted_value  DOUBLE PRECISION NOT NULL,
    lower_bound      DOUBLE PRECISION,
    upper_bound      DOUBLE PRECISION,
    confidence       DOUBLE PRECISION CHECK (confidence BETWEEN 0 AND 1),
    unit             TEXT,
    features         JSONB NOT NULL DEFAULT '{}'::jsonb,
    issued_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_at         TIMESTAMPTZ NOT NULL,
    CHECK (lower_bound IS NULL OR upper_bound IS NULL OR lower_bound <= upper_bound)
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft', 'validating', 'pending_approval', 'approved', 'rejected', 'active', 'completed', 'cancelled', 'invalidated')),
    objective        TEXT NOT NULL DEFAULT 'resilience',
    objective_value  DOUBLE PRECISION,
    assumptions      JSONB NOT NULL DEFAULT '{}'::jsonb,
    input_snapshot   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_from       TIMESTAMPTZ,
    valid_until      TIMESTAMPTZ,
    CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from)
);

CREATE TABLE IF NOT EXISTS plan_actions (
    action_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id          UUID NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    asset_id         TEXT NOT NULL REFERENCES grid_assets(asset_id) ON DELETE RESTRICT,
    action_type      TEXT NOT NULL,
    parameters       JSONB NOT NULL DEFAULT '{}'::jsonb,
    sequence_no      INTEGER NOT NULL DEFAULT 0 CHECK (sequence_no >= 0),
    starts_at        TIMESTAMPTZ,
    ends_at          TIMESTAMPTZ,
    expected_cost    DOUBLE PRECISION CHECK (expected_cost IS NULL OR expected_cost >= 0),
    expected_impact  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at >= starts_at)
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id          UUID REFERENCES plans(plan_id) ON DELETE SET NULL,
    decision_type    TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'proposed'
                     CHECK (status IN ('proposed', 'valid', 'invalid', 'superseded', 'executed')),
    rationale        TEXT NOT NULL DEFAULT '',
    validity_status  TEXT NOT NULL DEFAULT 'unverified'
                     CHECK (validity_status IN ('valid', 'at_risk', 'invalid', 'unverified')),
    validity_until   TIMESTAMPTZ,
    evidence         JSONB NOT NULL DEFAULT '[]'::jsonb,
    assumptions      JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id      UUID NOT NULL REFERENCES decisions(decision_id) ON DELETE CASCADE,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'rejected', 'withdrawn')),
    requested_by     TEXT,
    reviewer         TEXT,
    comment          TEXT NOT NULL DEFAULT '',
    requested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at      TIMESTAMPTZ,
    CHECK ((status = 'pending' AND resolved_at IS NULL) OR status <> 'pending')
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'waiting_approval')),
    input            JSONB NOT NULL DEFAULT '{}'::jsonb,
    output           JSONB NOT NULL DEFAULT '{}'::jsonb,
    error            TEXT,
    related_decision UUID REFERENCES decisions(decision_id) ON DELETE SET NULL,
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor            TEXT NOT NULL DEFAULT 'system',
    action           TEXT NOT NULL,
    entity_type      TEXT NOT NULL,
    entity_id        TEXT,
    before_state     JSONB,
    after_state      JSONB,
    details          JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL UNIQUE,
    description      TEXT NOT NULL DEFAULT '',
    model_name       TEXT,
    dataset_version  TEXT,
    configuration    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS benchmark_results (
    result_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id    UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    metric           TEXT NOT NULL,
    metric_value     DOUBLE PRECISION NOT NULL,
    sample_count     BIGINT CHECK (sample_count IS NULL OR sample_count >= 0),
    artifacts        JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (experiment_id, metric)
);

-- Persist create/solve responses so retries with the same request key do no new work.
CREATE TABLE IF NOT EXISTS idempotency_record (
    key              VARCHAR(255) PRIMARY KEY,
    request_hash     CHAR(64) NOT NULL,
    response_payload JSON NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_grid_assets_type_status ON grid_assets(asset_type, status);
CREATE INDEX IF NOT EXISTS idx_grid_assets_region ON grid_assets(region);
CREATE INDEX IF NOT EXISTS idx_grid_events_asset_observed ON grid_events(asset_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_grid_events_type_observed ON grid_events(event_type, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_grid_events_payload ON grid_events USING GIN(payload);
CREATE INDEX IF NOT EXISTS idx_source_records_asset_ingested ON source_records(asset_id, ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_records_payload ON source_records USING GIN(normalized_data);
CREATE INDEX IF NOT EXISTS idx_evidence_claims_record ON evidence_claims(record_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claims_asset_predicate ON evidence_claims(asset_id, predicate);
CREATE INDEX IF NOT EXISTS idx_constraints_active ON operational_constraints(active_from, active_until);
CREATE INDEX IF NOT EXISTS idx_forecasts_asset_valid ON forecasts(asset_id, valid_at DESC);
CREATE INDEX IF NOT EXISTS idx_plans_status_created ON plans(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plan_actions_plan_sequence ON plan_actions(plan_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_decisions_status_created ON decisions(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_approvals_status_requested ON approvals(status, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status_created ON agent_runs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_time ON audit_logs(entity_type, entity_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_experiment ON benchmark_results(experiment_id);
