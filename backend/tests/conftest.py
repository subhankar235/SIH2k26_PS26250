"""Environment defaults for backend test collection."""

from __future__ import annotations

import os

os.environ.setdefault("POSTGRES_USER", "airpower_test")
os.environ.setdefault("POSTGRES_PASSWORD", "airpower_test")
os.environ.setdefault("POSTGRES_DB", "airpower_test")
os.environ.setdefault("FRESHNESS_THRESHOLDS", '{"resource":3600,"crew":3600}')
