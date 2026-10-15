"""Database connection and repository helpers."""

import os
from typing import Any, Dict, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, desc
from .models import Base, OperationalEvent, MissionPlan, NegotiationTranscript

DEFAULT_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:postgres_password@127.0.0.1:5432/air_operations"
)

class StorageEngine:
    """Async database engine managing operational storage."""

    def __init__(self, db_url: str = DEFAULT_DATABASE_URL):
        self.db_url = db_url
        self.engine = create_async_engine(self.db_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def init_db(self) -> None:
        """Create tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Dispose of the database engine."""
        await self.engine.dispose()

    async def record_event(self, event_data: Dict[str, Any]) -> OperationalEvent:
        """Persist an operational event."""
        async with self.session_factory() as session:
            observed_at = event_data["observed_at"]
            if isinstance(observed_at, str):
                observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))

            valid_until = event_data["valid_until"]
            if isinstance(valid_until, str):
                valid_until = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))

            event = OperationalEvent(
                event_id=event_data["event_id"],
                event_type=event_data["event_type"],
                entity_id=event_data["entity_id"],
                source_id=event_data["source_id"],
                sequence=event_data["sequence"],
                observed_at=observed_at,
                valid_until=valid_until,
                payload=event_data.get("payload", {})
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)
            return event

    async def save_plan(self, plan_data: Dict[str, Any]) -> MissionPlan:
        """Persist a new operational mission plan."""
        async with self.session_factory() as session:
            plan = MissionPlan(
                run_id=plan_data["run_id"],
                revision=plan_data.get("revision", 0),
                status=plan_data.get("status", "optimal"),
                objective_score=float(plan_data.get("objective_score", 0.0)),
                served_priority=int(plan_data.get("served_priority", 0)),
                threat_risk_score=float(plan_data.get("threat_risk_score", 0.0)),
                assignments=plan_data.get("assignments", []),
                unserved=plan_data.get("unserved", []),
                diagnostics=plan_data.get("diagnostics", {})
            )
            session.add(plan)
            await session.commit()
            await session.refresh(plan)
            return plan

    async def record_transcripts(self, transcript_items: List[Dict[str, Any]]) -> List[NegotiationTranscript]:
        """Save a batch of MAGI agent negotiation transcripts."""
        async with self.session_factory() as session:
            records = []
            for item in transcript_items:
                record = NegotiationTranscript(
                    plan_id=item.get("plan_id"),
                    run_id=item["run_id"],
                    revision=item.get("revision", 0),
                    round_number=item.get("round_number", 1),
                    agent_name=item["agent_name"],
                    message_type=item["message_type"],
                    content=item["content"],
                    metadata_json=item.get("metadata", {})
                )
                session.add(record)
                records.append(record)
            await session.commit()
            return records

    async def get_latest_plan(self, run_id: Optional[str] = None) -> Optional[MissionPlan]:
        """Fetch the most recent mission plan."""
        async with self.session_factory() as session:
            query = select(MissionPlan).order_by(desc(MissionPlan.created_at))
            if run_id:
                query = query.where(MissionPlan.run_id == run_id)
            result = await session.execute(query)
            return result.scalars().first()

    async def get_recent_events(self, limit: int = 50) -> List[OperationalEvent]:
        """Fetch latest ingested events."""
        async with self.session_factory() as session:
            query = select(OperationalEvent).order_by(desc(OperationalEvent.observed_at)).limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())

