"""Estimate source reliability and per-claim belief from observed agreement."""

from __future__ import annotations

import importlib
from collections import defaultdict
from typing import Any
from uuid import UUID

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.claim import Claim, Issue
from backend.app.db.models.record import Record
from backend.app.db.models.source import Source


class ReliabilityEstimate(BaseModel):
    """Return posterior mean reliability and a credible interval."""

    model_config = ConfigDict(frozen=True)

    mean: float = Field(ge=0, le=1)
    hdi_low: float = Field(ge=0, le=1)
    hdi_high: float = Field(ge=0, le=1)


class ClaimBelief(BaseModel):
    """Return an evidence claim with source-derived belief weight."""

    model_config = ConfigDict(frozen=True)

    claim_id: UUID
    source_id: UUID
    attribute: str
    value: Any
    probability: float = Field(ge=0, le=1)


def _agreement_counts(db: Session) -> tuple[dict[UUID, int], dict[UUID, int]]:
    """Count per-source agreements and disagreements on comparable claims."""
    rows = db.execute(
        select(Claim, Record)
        .join(Record, Claim.record_id == Record.id)
        .where(Claim.superseded_by.is_(None), Record.superseded_by.is_(None))
    )
    groups: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for claim, record in rows:
        groups[(record.entity_id, claim.attribute)].append(claim)

    successes: dict[UUID, int] = defaultdict(int)
    failures: dict[UUID, int] = defaultdict(int)
    for claims in groups.values():
        if len({claim.source_id for claim in claims}) < 2:
            continue
        counts: dict[str, int] = defaultdict(int)
        for claim in claims:
            counts[repr(claim.value)] += 1
        highest = max(counts.values())
        winners = {value for value, count in counts.items() if count == highest}
        if len(winners) != 1:
            continue
        winner = next(iter(winners))
        for claim in claims:
            if repr(claim.value) == winner:
                successes[claim.source_id] += 1
            else:
                failures[claim.source_id] += 1
    return successes, failures


def source_reliability(db: Session, seed: int) -> dict[UUID, ReliabilityEstimate]:
    """Estimate source reliability using seeded Beta-Binomial posterior draws.

    Args:
        db: Active synchronous database session.
        seed: Seed for a local NumPy generator; global RNG state is untouched.

    Returns:
        Reliability estimates keyed by source UUID.
    """
    successes, failures = _agreement_counts(db)
    rng = np.random.default_rng(seed)
    estimates: dict[UUID, ReliabilityEstimate] = {}
    sources = db.scalars(select(Source).order_by(Source.id)).all()
    source_ids = [source.id for source in sources]

    try:
        bayesian_module = importlib.import_module("ml.bayesian.source_reliability")
        fit = getattr(bayesian_module, "fit", None)
        if callable(fit) and source_ids:
            import pandas as pd  # type: ignore[import-untyped]

            observations = pd.DataFrame(
                [
                    {
                        "source_id": str(source_id),
                        "successes": successes.get(source_id, 0),
                        "failures": failures.get(source_id, 0),
                    }
                    for source_id in source_ids
                ]
            )
            inference_data = fit(observations, seed=seed)
            posterior = inference_data.posterior
            parameter = next(
                name for name in ("reliability", "source_reliability") if name in posterior
            )
            draws = np.asarray(posterior[parameter])
            draws = draws.reshape((-1, len(source_ids)))
            for index, source_id in enumerate(source_ids):
                source_draws = draws[:, index]
                low, high = np.quantile(source_draws, [0.05, 0.95]).tolist()
                estimates[source_id] = ReliabilityEstimate(
                    mean=float(np.mean(source_draws)),
                    hdi_low=float(low),
                    hdi_high=float(high),
                )
            return estimates
    except (ImportError, AttributeError, KeyError, StopIteration):
        # PyMC, pandas, or the optional model module is unavailable; use conjugate fallback.
        estimates.clear()

    for source in sources:
        prior = min(1.0, max(0.0, source.reliability_prior))
        alpha = max(0.1, 4.0 * prior) + successes.get(source.id, 0)
        beta = max(0.1, 4.0 * (1.0 - prior)) + failures.get(source.id, 0)
        draws = rng.beta(alpha, beta, size=4096)
        low, high = np.quantile(draws, [0.05, 0.95]).tolist()
        estimates[source.id] = ReliabilityEstimate(
            mean=alpha / (alpha + beta),
            hdi_low=float(low),
            hdi_high=float(high),
        )
    return estimates


def claim_belief(
    issue: Issue,
    reliabilities: dict[UUID, ReliabilityEstimate],
) -> list[ClaimBelief]:
    """Attach source reliability estimates to claims serialized in an issue.

    Args:
        issue: Evidence issue carrying claim ids and claim summaries in details.
        reliabilities: Per-source posterior estimates.

    Returns:
        Claim beliefs sorted by claim UUID.
    """
    claim_details = issue.details.get("claims", [])
    beliefs: list[ClaimBelief] = []
    for item in claim_details:
        try:
            source_id = UUID(str(item["source_id"]))
            claim_id = UUID(str(item["claim_id"]))
        except (KeyError, TypeError, ValueError):
            continue
        estimate = reliabilities.get(source_id)
        if estimate is None:
            continue
        beliefs.append(
            ClaimBelief(
                claim_id=claim_id,
                source_id=source_id,
                attribute=str(item.get("attribute", "")),
                value=item.get("value"),
                probability=estimate.mean,
            )
        )
    return sorted(beliefs, key=lambda belief: str(belief.claim_id))
