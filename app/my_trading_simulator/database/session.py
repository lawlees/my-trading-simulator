
from pathlib import Path
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "trading_simulator.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "timeout": 5,
    },
)


@event.listens_for(engine, "connect")
def configure_sqlite_connection(dbapi_connection, connection_record):
    """Configure each new SQLite connection."""

    if not isinstance(dbapi_connection, sqlite3.Connection):
        return

    cursor = dbapi_connection.cursor()

    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.execute("PRAGMA foreign_keys = ON")

    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def enable_wal_mode():
    """Enable SQLite write-ahead logging."""

    with engine.connect() as connection:
        result = connection.exec_driver_sql(
            "PRAGMA journal_mode=WAL"
        )
        return result.scalar()
