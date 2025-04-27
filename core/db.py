# core/db.py
import os
from sqlmodel import SQLModel, create_engine

# pick up the same URL your API container will use
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:pass@localhost:5432/postgres",
)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

def init_db() -> None:
    """Create all tables (dev only).  In prod we rely on Alembic."""
    import core.models  # noqa: F401  (ensures models are registered)
    SQLModel.metadata.create_all(engine)
