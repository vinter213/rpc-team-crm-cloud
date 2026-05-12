import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = Path(__file__).resolve().parent

# For Koyeb Free test version SQLite is used by default.
# For later PostgreSQL, set DATABASE_URL in Koyeb environment variables.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    SQLALCHEMY_DATABASE_URL = DATABASE_URL
    connect_args = {}
else:
    DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR))).resolve()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = DATA_DIR / "rpc_team_crm.db"
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
    connect_args = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
