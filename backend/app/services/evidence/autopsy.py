"""Build evidence autopsies with claims, provenance, and uncertainty."""

from __future__ import annotations

from uuid import UUID

import networkx as nx  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.exceptions import NotFoundError
from backend.app.db.models.claim import Claim, Issue
from backend.app.db.models.record import Record
from backend.app.schemas.evidence import AutopsyOut, ClaimOut, IssueOut, ProvenanceStep
from backend.app.services.evidence.evidence_graph import build_graph
from backend.app.services.evidence.provenance_tracer import trace
from backend.app.services.evidence.uncertainty import claim_belief, source_reliability
from backend.app.services.ingestion.normaliser import to_utc


def missing_information(issue: Issue, g: nx.MultiDiGraph) -> list[str]:
    """List missing fields and evidence links relevant to an issue.

    Args:
        issue: Persisted evidence issue.
        g: Evidence graph used to check linked records and claims.

    Returns:
        Human-readable missing-information items without duplicates.
    """
    missing = [str(value) for value in issue.details.get("missing_fields", [])]
    if issue.issue_class == "missing" and not missing:
        missing.append("The issue has no explicit missing-field details.")

    for claim_id in issue.claim_ids:
        node_id = f"claim:{claim_id}"
        if node_id not in g:
            missing.append(f"Claim {claim_id} is not present in the evidence graph.")

    if not issue.claim_ids and issue.issue_class in {"conflict", "duplicate"}:
        missing.append("No supporting claim ids are linked to this issue.")
    return list(dict.fromkeys(missing))


def build_autopsy(db: Session, issue_id: UUID) -> AutopsyOut:
    """Build a full issue explanation from claims, graph provenance, and reliability.

    Args:
        db: Active synchronous database session.
        issue_id: UUID of the issue to explain.

    Returns:
        Competing claims, provenance timeline, missing information, and uncertainty.

    Raises:
        NotFoundError: If the requested issue does not exist.
    """
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise NotFoundError("Issue not found", {"id": str(issue_id)})

    try:
        claim_ids = [UUID(str(value)) for value in issue.claim_ids]
    except ValueError:
        claim_ids = []
    claims = (
        list(
            db.scalars(
                select(Claim).where(Claim.id.in_(claim_ids)).order_by(Claim.observed_at, Claim.id)
            )
        )
        if claim_ids
        else []
    )

    record_ids = {claim.record_id for claim in claims}
    record_ids.update(
        UUID(value)
        for value in [issue.details.get("record_id")]
        if isinstance(value, str) and _is_uuid(value)
    )
    records = (
        list(db.scalars(select(Record).where(Record.id.in_(record_ids)))) if record_ids else []
    )
    entity_ids = sorted({record.entity_id for record in records})
    graph = build_graph(db, entity_ids or None)

    claim_out = [
        ClaimOut(
            id=claim.id,
            record_id=claim.record_id,
            attribute=claim.attribute,
            value=claim.value,
            source_id=claim.source_id,
            observed_at=to_utc(claim.observed_at),
            superseded_by=claim.superseded_by,
        )
        for claim in claims
    ]
    provenance: list[ProvenanceStep] = []
    seen_steps: set[tuple[UUID, str, int | None]] = set()
    for record_id in sorted(record_ids, key=str):
        for step in trace(db, record_id):
            key = (step.record_id, step.action, step.version)
            if key not in seen_steps:
                seen_steps.add(key)
                provenance.append(step)
    provenance.sort(key=lambda step: (step.timestamp, step.version or 0, step.action))

    reliability = source_reliability(db, seed=get_settings().random_seed)
    beliefs = claim_belief(issue, reliability)
    uncertainty = {
        "sources": {
            str(source_id): estimate.model_dump()
            for source_id, estimate in sorted(reliability.items(), key=lambda item: str(item[0]))
        },
        "claims": [belief.model_dump(mode="json") for belief in beliefs],
    }
    return AutopsyOut(
        issue=IssueOut(
            id=issue.id,
            issue_class=issue.issue_class,
            claim_ids=[UUID(str(value)) for value in issue.claim_ids],
            detected_at=to_utc(issue.detected_at),
            status=issue.status,
            details=issue.details,
        ),
        claims=claim_out,
        provenance=provenance,
        missing_information=missing_information(issue, graph),
        uncertainty=uncertainty,
    )


def _is_uuid(value: str) -> bool:
    """Return whether a string parses as a UUID."""
    try:
        UUID(value)
    except ValueError:
        return False
    return True
