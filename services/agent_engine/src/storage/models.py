"""SQLAlchemy models for PostgreSQL storage."""

from datetime import datetime
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import String, Integer, Float, DateTime, Text, JSON, func, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative model."""
    pass


class OperationalEvent(Base):
    """Stores ingested operational domain events."""
    __tablename__ = "operational_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(String(36), index=True, unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MissionPlan(Base):
    """Stores generated operational schedules and revisions."""
    __tablename__ = "mission_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # optimal, feasible_budget, infeasible, historical
    objective_score: Mapped[float] = mapped_column(Float, default=0.0)
    served_priority: Mapped[int] = mapped_column(Integer, default=0)
    threat_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    assignments: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    unserved: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    diagnostics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transcripts: Mapped[List["NegotiationTranscript"]] = relationship("NegotiationTranscript", back_populates="plan", cascade="all, delete-orphan")


class NegotiationTranscript(Base):
    """Stores MAGI multi-agent negotiation logs and debate records."""
    __tablename__ = "negotiation_transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("mission_plans.id"), nullable=True, index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)  # PROPOSAL, ACCEPT, OBJECTION, COUNTER_BID, VERDICT
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan: Mapped[Optional["MissionPlan"]] = relationship("MissionPlan", back_populates="transcripts")

