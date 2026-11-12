from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


# Project root: my-trading-simulator/
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Local database directory
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite database
DATABASE_PATH = DATA_DIR / "trading_simulator.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Database engine
engine = create_engine(
    DATABASE_URL,
    echo=False,
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)