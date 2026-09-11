import os
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config.settings import settings

logger = logging.getLogger("agentos.db")

# In SQLite, thread-local connections are important.
# check_same_thread=False is required to use connections across threads
# safely when each thread uses its own Session object.


def get_db_dialect() -> str:
    """Return database dialect ('postgresql' or 'sqlite')."""
    url = settings.DATABASE_URL.lower()
    if url.startswith("postgresql") or url.startswith("postgres"):
        return "postgresql"
    return "sqlite"


def _ensure_sqlite_directory() -> None:
    """Create the parent directory for the SQLite database file if it doesn't exist.

    The DATABASE_URL may be a relative path (e.g. ``sqlite:///./data/agentos.db``).
    We resolve it relative to the repository root so that both development runs and
    CI runs write to the same predictable location rather than wherever the process
    happens to have been launched from.
    """
    url = make_url(settings.DATABASE_URL)
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:") or url.query.get("uri"):
        return

    # Strip the sqlite:/// prefix; the remainder is the file path.
    raw_path = url.database

    # Resolve relative paths from the repository root (PROJECT_ROOT), not CWD.
    from backend.app.config.settings import PROJECT_ROOT  # local import avoids circular
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / raw_path

    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.debug("SQLite database directory ensured: %s", db_path.parent)


connect_args = {}
engine_kwargs: dict = {
    "pool_pre_ping": True,
}

if get_db_dialect() == "sqlite":
    connect_args["check_same_thread"] = False
    engine_kwargs["connect_args"] = connect_args
else:
    # PostgreSQL production connection pooling
    engine_kwargs["pool_size"] = getattr(settings, "DB_POOL_SIZE", 10)
    engine_kwargs["max_overflow"] = getattr(settings, "DB_MAX_OVERFLOW", 20)
    engine_kwargs["pool_recycle"] = getattr(settings, "DB_POOL_RECYCLE_SECONDS", 300)
    engine_kwargs["pool_timeout"] = getattr(settings, "DB_POOL_TIMEOUT_SECONDS", 30)

engine = create_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db() -> None:
    """Create all database tables that are not yet present.

    This is the **only** place that should call ``Base.metadata.create_all``.
    It must be called explicitly:

    * From the FastAPI application lifespan handler on startup.
    * From the pytest session fixture in ``conftest.py`` before tests run.

    Importing ORM models (``backend.app.db.models``) must never trigger this
    as a side effect.  The models module only defines the schema; it does NOT
    initialize the database.
    """
    # Import models here so that all ORM classes are registered on Base.metadata
    # before create_all runs.  This import is intentionally deferred to avoid
    # circular imports at module load time.
    import backend.app.db.models as _models  # noqa: F401  (side-effect: registers models)

    _ensure_sqlite_directory()
    logger.info("Initializing database schema (create_all)...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ready.")


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
