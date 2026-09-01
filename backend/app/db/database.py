import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config.settings import settings

# In SQLite, thread-local connections are important. 
# check_same_thread=False is often used but sessions shouldn't be shared across threads.
# We will use connection pooling specifically configured for our needs.
# Actually, since SQLAlchemy manages connection pools, check_same_thread=False
# is required if we want to use the connection across different async workers
# or thread workers, but we must ensure we don't share Session objects.

def get_db_dialect() -> str:
    """Return database dialect ('postgresql' or 'sqlite')."""
    url = settings.DATABASE_URL.lower()
    if url.startswith("postgresql") or url.startswith("postgres"):
        return "postgresql"
    return "sqlite"


connect_args = {}
engine_kwargs = {
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
