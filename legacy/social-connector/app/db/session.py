# Social Connector - Database Session

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from typing import Generator
import os

from app.config import get_settings

# Global engine and session factory
_engine = None
_session_factory = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        # For SQLite, we need check_same_thread=False for multi-threaded access
        connect_args = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        
        _engine = create_engine(
            settings.database_url,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            connect_args=connect_args,
            poolclass=StaticPool if settings.database_url.startswith("sqlite") else None,
        )
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _session_factory


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Get a database session with automatic commit/rollback."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Initialize database tables."""
    from app.core.models import Base
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def reset_db():
    """Drop and recreate all tables (for testing)."""
    from app.core.models import Base
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)