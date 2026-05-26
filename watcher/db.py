"""
SQLite database engine and session factory.
"""

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base

# SQLite database file path
DATABASE_URL = "sqlite:///./data/apiwatcher.db"

# Create engine with check_same_thread=False for concurrent access from scheduler + API
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False  # Set to True for SQL query logging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    Initialize database by creating all tables.
    Should be called on application startup.
    """
    Base.metadata.create_all(bind=engine)
    print("✓ Database initialized")


@contextmanager
def get_db() -> Session:
    """
    Context manager for database sessions.

    Usage:
        with get_db() as db:
            endpoint = db.query(Endpoint).first()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """
    Get a new database session.
    Caller is responsible for closing the session.

    Usage (FastAPI dependency):
        def some_endpoint(db: Session = Depends(get_db_session)):
            ...

    Don't forget to close the session when done!
    """
    return SessionLocal()
