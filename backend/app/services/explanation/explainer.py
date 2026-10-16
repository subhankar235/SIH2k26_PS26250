"""Build explanations from persisted agent output and resolve every citation."""

from __future__ import annotations

import re
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import NotFoundError, VerificationFailed
from backend.app.db.models.agent_run import AgentRun
from backend.app.db.models.approval import Approval, VerificationResult
from backend.app.db.models.audit_log import AuditEntry
from backend.app.db.models.claim import Claim, EvidenceEdge, Issue
from backend.app.db.models.decision import Assumption, Decision, Dependency
from backend.app.db.models.experiment import ExperimentRun
from backend.app.db.models.forecast import Forecast
from backend.app.db.models.record import RawEvent, Record
from backend.app.db.models.schedule import Schedule
from backend.app.db.models.source import Source
from backend.app.schemas.agents import EvidenceRef, ExplanationOut

_CITATION = re.compile(
    r"\[(?P<kind>[A-Za-z][A-Za-z0-9_-]*):(?P<id>[0-9a-fA-F-]{36}):v(?P<version>[1-9][0-9]*)\]"
)
_INLINE_CITATION_SHAPE = re.compile(r"\[[A-Za-z][A-Za-z0-9_-]*:[^\]]*:v\d+\]")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def _exists_at_version(db: Session, ref: EvidenceRef) -> bool:
    """Resolve a citation kind/id and compare its authoritative stored version."""
    kind = ref.kind.strip().casefold()
    if kind == "record":
        record = db.get(Record, ref.id)
        return record is not None and record.version == ref.version
    if kind == "forecast":
        forecast = db.get(Forecast, ref.id)
        return forecast is not None and forecast.version == ref.version
    if kind == "schedule":
        schedule = db.get(Schedule, ref.id)
        return schedule is not None and schedule.version == ref.version
    if kind == "decision":
        decision = db.get(Decision, ref.id)
        return decision is not None and decision.version == ref.version
    if kind == "claim":
        claim = db.get(Claim, ref.id)
        record = db.get(Record, claim.record_id) if claim is not None else None
        return record is not None and record.version == ref.version

    immutable_models = {
        "approval": Approval,
        "audit": AuditEntry,
        "audit_entry": AuditEntry,
        "agent_run": AgentRun,
        "dependency": Dependency,
        "evidence_edge": EvidenceEdge,
        "experiment_run": ExperimentRun,
        "issue": Issue,
        "raw_event": RawEvent,
        "source": Source,
        "verification": VerificationResult,
        "verification_result": VerificationResult,
        "assumption": Assumption,
    }
    model = immutable_models.get(kind)
    return model is not None and ref.version == 1 and db.get(model, ref.id) is not None


def _sentences(text: str) -> list[str]:
    """Split explanation prose into non-empty claim sentences."""
    return [part.strip() for part in _SENTENCE_BOUNDARY.split(text.strip()) if part.strip()]


def validate_citations(db: Session, text: str, refs: list[EvidenceRef]) -> list[str]:
    """Return unresolved evidence refs and sentence-to-citation mapping errors.

    Evidence refs without inline markers apply to every claim sentence, matching
    ``ExplanationOut``'s explanation-level citation contract. If inline markers are
    used, each sentence must carry at least one marker of the form
    ``[kind:uuid:vN]`` and each marker must occur in ``refs``.

    Args:
        db: Active synchronous database session.
        text: Explanation text, optionally containing inline evidence markers.
        refs: Versioned references supplied with the explanation.

    Returns:
        Deduplicated unresolved refs and citation-mapping problems.
    """
    unresolved: list[str] = []
    refs_by_key = {
        (ref.kind.strip().casefold(), ref.id, ref.version): ref
        for ref in refs
    }
    if not refs:
        unresolved.append("explanation has no evidence references")
    for ref in refs:
        if not _exists_at_version(db, ref):
            unresolved.append(f"{ref.kind}:{ref.id}:v{ref.version}")

    sentences = _sentences(text)
    if not sentences:
        unresolved.append("explanation text has no claim sentences")
    has_inline_citations = bool(_INLINE_CITATION_SHAPE.search(text))
    if has_inline_citations:
        for index, sentence in enumerate(sentences, start=1):
            markers = list(_CITATION.finditer(sentence))
            if not markers:
                unresolved.append(f"sentence {index}: missing inline evidence citation")
                continue
            for marker in markers:
                try:
                    key = (
                        marker.group("kind").casefold(),
                        UUID(marker.group("id")),
                        int(marker.group("version")),
                    )
                except ValueError:
                    unresolved.append(f"sentence {index}: malformed evidence citation")
                    continue
                if key not in refs_by_key:
                    unresolved.append(
                        f"sentence {index}: unlisted citation "
                        f"{marker.group('kind')}:{marker.group('id')}:v{marker.group('version')}"
                    )
    return list(dict.fromkeys(unresolved))


def _explanation_payload(run: AgentRun) -> object:
    """Read the latest explanation from the dedicated output or graph state."""
    if run.explanation:
        return run.explanation
    graph_explanation = run.graph_state.get("explanation")
    return graph_explanation if graph_explanation is not None else {}


def build_explanation(db: Session, run: AgentRun) -> ExplanationOut:
    """Validate persisted agent claims and return only resolvable evidence citations.

    Args:
        db: Active synchronous database session.
        run: Persisted agent run containing explanation text and evidence refs.

    Returns:
        Validated explanation with its evidence references.

    Raises:
        VerificationFailed: If output is malformed, uncited, or cites missing/stale evidence.
    """
    payload = _explanation_payload(run)
    if not isinstance(payload, dict):
        raise VerificationFailed(
            "Agent explanation is malformed", {"run_id": str(run.id)}
        )
    try:
        explanation = ExplanationOut.model_validate(payload)
    except ValidationError as error:
        raise VerificationFailed(
            "Agent explanation does not satisfy the explanation schema",
            {"run_id": str(run.id), "reason": str(error)},
        ) from error
    unresolved = validate_citations(db, explanation.text, explanation.evidence_refs)
    if unresolved:
        raise VerificationFailed(
            "Agent explanation contains unresolved evidence citations",
            {"run_id": str(run.id), "unresolved_refs": unresolved},
        )
    return explanation


def get_explanation(db: Session, run_id: UUID) -> ExplanationOut:
    """Load an agent run and return its citation-validated explanation.

    Args:
        db: Active synchronous database session.
        run_id: Agent run UUID.

    Returns:
        The validated explanation and evidence refs.

    Raises:
        NotFoundError: If the agent run does not exist.
        VerificationFailed: If the persisted explanation cannot be grounded.
    """
    run = db.get(AgentRun, run_id)
    if run is None:
        raise NotFoundError("Agent run not found", {"id": str(run_id)})
    return build_explanation(db, run)
