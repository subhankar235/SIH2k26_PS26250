CREATE TABLE IF NOT EXISTS grid_assets (
    asset_id TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL,
    capacity_mw DOUBLE PRECISION NOT NULL CHECK (capacity_mw >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS grid_events (
    event_id BIGSERIAL PRIMARY KEY,
    asset_id TEXT REFERENCES grid_assets(asset_id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
