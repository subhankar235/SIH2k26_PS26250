"""Synchronous SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings

engine: Engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def session_scope() -> Iterator[Session]:
    """Yield a session and manage its transaction for scripts and consumers.

    Yields:
        A synchronous SQLAlchemy session.

    Raises:
        Exception: Re-raises any error after rolling back the transaction.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
