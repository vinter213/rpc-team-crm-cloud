import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ============================================================
# RPC Team CRM database
# ============================================================
# If DATABASE_URL exists in Render Environment, server uses
# permanent PostgreSQL database, for example Supabase.
#
# If DATABASE_URL is empty, server falls back to local SQLite.
# Local SQLite on Render can be reset after redeploy/restart,
# so for production use DATABASE_URL.
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    # Render/Supabase sometimes provides postgres://,
    # SQLAlchemy wants postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
    )
else:
    SQLITE_PATH = os.getenv("SQLITE_PATH", "rpc_team_crm.db")
    engine = create_engine(
        f"sqlite:///{SQLITE_PATH}",
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """
    FastAPI dependency.
    Opens database session and closes it after request.
    main.py imports this function.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
