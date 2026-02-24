"""
PostgreSQL database configuration using SQLAlchemy.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()


def get_database_url() -> str:
    return (
        f"postgresql+psycopg2://"
        f"{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
        f"/{os.getenv('DB_NAME', 'trading_sim')}"
    )


engine = create_engine(get_database_url(), echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session():
    """Context-managed database session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create all tables if they don't exist, and apply incremental column migrations."""
    from db.models import Base as ModelsBase  # noqa: F401 - triggers table registration
    ModelsBase.metadata.create_all(bind=engine)
    _migrate_columns()


def _migrate_columns():
    """Idempotent: add new columns to existing tables when the schema evolves."""
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE executions ADD COLUMN IF NOT EXISTS stop_loss_price NUMERIC(12,4)",
        "ALTER TABLE executions ADD COLUMN IF NOT EXISTS profit_target_price NUMERIC(12,4)",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            conn.execute(text(stmt))
        conn.commit()
