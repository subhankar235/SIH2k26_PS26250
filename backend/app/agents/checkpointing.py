"""PostgreSQL LangGraph checkpoint saver construction with an offline fallback."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.engine import make_url

_MEMORY_SAVERS: dict[str, InMemorySaver] = {}
_MEMORY_LOCK = Lock()


@contextmanager
def get_checkpointer(db_url: str) -> Iterator[BaseCheckpointSaver[Any]]:
    """Yield a persistent PostgreSQL saver or an in-memory saver for local SQLite.

    PostgreSQL saver setup is run before the graph is compiled. The saver and its
    underlying connection pool are closed when the workflow invocation completes.
    """
    url = make_url(db_url)
    if url.get_backend_name() != "postgresql":
        key = url.render_as_string(hide_password=True)
        with _MEMORY_LOCK:
            saver = _MEMORY_SAVERS.setdefault(key, InMemorySaver())
        yield saver
        return
    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "PostgreSQL agent checkpoints require langgraph-checkpoint-postgres"
        ) from error
    psycopg_url = url.set(drivername="postgresql").render_as_string(hide_password=False)
    with PostgresSaver.from_conn_string(psycopg_url) as saver:
        saver.setup()
        yield saver
