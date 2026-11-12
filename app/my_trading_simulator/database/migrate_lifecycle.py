
import sqlite3
from datetime import datetime
from pathlib import Path

from my_trading_simulator.database.session import DATABASE_PATH


def migrate_lifecycle():
    database_path = Path(DATABASE_PATH)

    if not database_path.exists():
        raise FileNotFoundError(
            f"Database does not exist: {database_path}"
        )

    # Step 1: Create backup directory
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: Create timestamped database backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"trading_simulator_{timestamp}.db"

    # SQLite backup API creates a consistent database snapshot
    with sqlite3.connect(database_path) as source:
        with sqlite3.connect(backup_path) as backup:
            source.backup(backup)

    print(f"Backup created: {backup_path}")

    # Step 3: Check existing database columns
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(option_positions)"
            )
        }

        if not columns:
            raise RuntimeError("option_positions table not found")

        # Step 4: Add profit_take_completed
        if "profit_take_completed" not in columns:
            connection.execute(
                """
                ALTER TABLE option_positions
                ADD COLUMN profit_take_completed
                BOOLEAN NOT NULL DEFAULT 0
                """
            )
            print("Added: profit_take_completed")
        else:
            print("Already exists: profit_take_completed")

        # Step 5: Add runner_stop_price
        if "runner_stop_price" not in columns:
            connection.execute(
                """
                ALTER TABLE option_positions
                ADD COLUMN runner_stop_price NUMERIC(12, 4)
                """
            )
            print("Added: runner_stop_price")
        else:
            print("Already exists: runner_stop_price")

        # Step 6: Add profit_take_status
        if "profit_take_status" not in columns:
            connection.execute(
                """
                ALTER TABLE option_positions
                ADD COLUMN profit_take_status
                VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                """
            )
            print("Added: profit_take_status")
        else:
            print("Already exists: profit_take_status")

        # Step 7: Save changes
        connection.commit()

    print("Lifecycle migration completed successfully")


if __name__ == "__main__":
    migrate_lifecycle()
