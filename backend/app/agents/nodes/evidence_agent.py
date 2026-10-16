"""Evidence collection node using deterministic evidence services only."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.agents.nodes.common import step
from backend.app.agents.state import AgentState, EvidenceSummary, current_session
from backend.app.schemas.agents import EvidenceRef
from backend.app.services.evidence.autopsy import build_autopsy
from backend.app.services.evidence.contradiction_detector import detect_all


def run(state: AgentState, db: Session | None = None) -> AgentState:
    """Detect evidence issues and build bounded autopsies for the workflow context."""
    session = current_session(db)
    issues = detect_all(session, datetime.now(UTC))
    issue_ids = [issue.id for issue in issues]
    refs: list[EvidenceRef] = []
    autopsies: list[dict[str, object]] = []
    class_counts: dict[str, int] = {}
    for issue in issues:
        class_counts[issue.issue_class] = class_counts.get(issue.issue_class, 0) + 1
        refs.append(EvidenceRef(kind="issue", id=issue.id, version=1))
        if len(autopsies) < 20:
            autopsies.append(build_autopsy(session, issue.id).model_dump(mode="json"))
    summary = EvidenceSummary(
        issue_ids=issue_ids,
        issue_classes=class_counts,
        evidence_refs=list({(ref.kind, ref.id, ref.version): ref for ref in refs}.values()),
        autopsies=autopsies,
    )
    return state.model_copy(
        update={
            "evidence": summary,
            "evidence_refs": summary.evidence_refs,
            "steps": step(state, "evidence", "completed", issue_count=len(issues)),
        }
    )
