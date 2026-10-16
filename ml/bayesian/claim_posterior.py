"""Posterior probabilities that evidence claims are the correct assertion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import arviz as az


@dataclass(frozen=True)
class ClaimObs:
    """One source's value assertion for an entity attribute."""

    claim_id: str
    source_id: str
    entity_id: str
    attribute: str
    value: Any


@dataclass(frozen=True)
class ClaimPosterior:
    """Posterior probability and central credible interval for one claim value."""

    claim_id: str
    probability: float
    hdi_low: float
    hdi_high: float


def _canonical(value: Any) -> str:
    """Serialize values deterministically for claim comparison."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return repr(value)


def _hdi(samples: np.ndarray, mass: float = 0.9) -> tuple[float, float]:
    """Return a shortest empirical interval containing the requested posterior mass."""
    ordered = np.sort(np.asarray(samples, dtype=np.float64).reshape(-1))
    if not len(ordered):
        raise ValueError("posterior samples are empty")
    interval_count = max(1, int(np.ceil(mass * len(ordered))))
    if interval_count >= len(ordered):
        return float(ordered[0]), float(ordered[-1])
    widths = ordered[interval_count - 1 :] - ordered[: len(ordered) - interval_count + 1]
    start = int(np.argmin(widths))
    return float(ordered[start]), float(ordered[start + interval_count - 1])


def _reliability_draws(idata: az.InferenceData) -> tuple[np.ndarray, dict[str, int]]:
    """Extract reliability draws and their source coordinate from InferenceData."""
    if not hasattr(idata, "posterior") or "reliability" not in idata.posterior:
        raise ValueError("inference data must contain posterior reliability samples")
    variable = idata.posterior["reliability"]
    source_dimension = next(
        (dimension for dimension in variable.dims if dimension not in {"chain", "draw"}),
        None,
    )
    if source_dimension is None or source_dimension not in idata.posterior.coords:
        raise ValueError("reliability posterior must include a labeled source dimension")
    sources = [str(value) for value in idata.posterior.coords[source_dimension].values]
    values = variable.transpose("chain", "draw", source_dimension).values
    draws = np.asarray(values, dtype=np.float64).reshape(-1, len(sources))
    if not np.isfinite(draws).all() or ((draws < 0) | (draws > 1)).any():
        raise ValueError("reliability posterior draws must be finite probabilities")
    return draws, {source_id: index for index, source_id in enumerate(sources)}


def posterior_for_claims(
    idata: az.InferenceData,
    claims: list[ClaimObs],
) -> list[ClaimPosterior]:
    """Combine source-reliability draws into competing-claim value posteriors.

    Claims are grouped by entity and attribute. For each posterior draw, the
    likelihood of each candidate value is the product of source reliability for
    supporting claims and the remaining probability divided across alternatives
    for disagreeing claims. A softmax over candidate values yields each claim's
    posterior truth probability.
    """
    if not claims:
        return []
    claim_ids = [str(claim.claim_id) for claim in claims]
    if len(set(claim_ids)) != len(claims):
        raise ValueError("claim_id values must be unique")
    for claim in claims:
        if not all((claim.claim_id, claim.source_id, claim.entity_id, claim.attribute)):
            raise ValueError("claim identifiers, entity_id, and attribute must be non-empty")
    reliability, source_indexes = _reliability_draws(idata)
    unknown_sources = sorted({str(claim.source_id) for claim in claims} - set(source_indexes))
    if unknown_sources:
        raise ValueError(f"claims refer to sources without posterior estimates: {unknown_sources}")

    groups: dict[tuple[str, str], list[ClaimObs]] = {}
    for claim in claims:
        groups.setdefault((str(claim.entity_id), str(claim.attribute)), []).append(claim)
    output: dict[str, ClaimPosterior] = {}
    epsilon = np.finfo(np.float64).eps
    for group_claims in groups.values():
        value_keys = list(dict.fromkeys(_canonical(claim.value) for claim in group_claims))
        log_likelihood = np.zeros((len(reliability), len(value_keys)), dtype=np.float64)
        for claim in group_claims:
            source_draw = np.clip(
                reliability[:, source_indexes[str(claim.source_id)]], epsilon, 1 - epsilon
            )
            for index, candidate in enumerate(value_keys):
                if candidate == _canonical(claim.value):
                    log_likelihood[:, index] += np.log(source_draw)
                else:
                    alternative_probability = (1.0 - source_draw) / max(1, len(value_keys) - 1)
                    log_likelihood[:, index] += np.log(
                        np.clip(alternative_probability, epsilon, 1.0)
                    )
        log_likelihood -= log_likelihood.max(axis=1, keepdims=True)
        candidate_probabilities = np.exp(log_likelihood)
        candidate_probabilities /= candidate_probabilities.sum(axis=1, keepdims=True)
        candidate_indexes = {value: index for index, value in enumerate(value_keys)}
        for claim in group_claims:
            samples = candidate_probabilities[:, candidate_indexes[_canonical(claim.value)]]
            low, high = _hdi(samples)
            output[claim.claim_id] = ClaimPosterior(
                claim_id=str(claim.claim_id),
                probability=float(samples.mean()),
                hdi_low=low,
                hdi_high=high,
            )
    return [output[claim_id] for claim_id in claim_ids]
