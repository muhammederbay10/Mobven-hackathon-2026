"""Database engine, session lifecycle and UTC timestamp helpers.

Plan section 7.1: "Use SQLModel with explicit enums and UTC timestamps."
Every timestamp written by this service is timezone-aware UTC, and every
timestamp serialized to the API is an ISO-8601 instant with a literal ``Z``,
matching the format frozen in ``docs/CONTRACT_FREEZE.md``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from api.config import Settings, get_settings

_engine: Engine | None = None


# ---------------------------------------------------------------------------
# UTC helpers
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """The single source of 'now' for the service. Always timezone-aware UTC."""
    return datetime.now(UTC)


def to_iso_instant(value: datetime) -> str:
    """Serialize to the frozen instant format: `2026-08-01T10:00:00Z`.

    A naive datetime is treated as UTC — SQLite round-trips drop tzinfo, so rows
    read back from the database arrive naive even though they were stored in UTC.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def to_iso_date(value: datetime) -> str:
    """Serialize to the frozen calendar-date format: `2026-08-01`."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).date().isoformat()


# ---------------------------------------------------------------------------
# Engine and sessions
# ---------------------------------------------------------------------------


def get_engine(settings: Settings | None = None) -> Engine:
    """Process-wide engine. Created lazily so tests can point at a temp database."""
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        _engine = create_engine(
            settings.sqlalchemy_url,
            echo=False,
            # FastAPI serves requests from a thread pool; SQLite's default
            # same-thread check would reject those connections.
            connect_args={"check_same_thread": False},
        )
        _configure_sqlite(_engine)
    return _engine


def reset_engine() -> None:
    """Dispose the cached engine. Used by tests and by a full demo reset."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def _configure_sqlite(engine: Engine) -> None:
    """Enforce foreign keys, which SQLite leaves off by default.

    Without this the FK columns below are decorative, and a reset could leave
    orphaned documents or extractions behind — exactly the kind of silent drift
    that makes a demo irreproducible.
    """

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: object, _record: object) -> None:  # pragma: no cover
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on any exception.

    Plan section 15: "Audit-write failure: roll back the material business
    action." Business work and its audit rows therefore share one scope.
    """
    with Session(get_engine()) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


# ---------------------------------------------------------------------------
# Schema lifecycle
# ---------------------------------------------------------------------------


def init_db(settings: Settings | None = None) -> None:
    """Create every table if missing. Safe to call repeatedly."""
    settings = settings or get_settings()
    # Importing for the side effect of registering the tables on SQLModel.metadata.
    from api import models  # noqa: F401

    database_path = settings.database_path
    if database_path is not None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(get_engine(settings))


def drop_all(settings: Settings | None = None) -> None:
    """Drop every table. Only ever called by the demo reset service."""
    settings = settings or get_settings()
    from api import models  # noqa: F401

    SQLModel.metadata.drop_all(get_engine(settings))
