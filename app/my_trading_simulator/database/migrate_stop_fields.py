
"""
Non-destructive SQLite migration.

Adds stop-loss fields to existing option positions.
Run only after backing up the database.
"""

import sqlite3

from my_trading_simulator.database.session import DATABASE_PATH


def migrate():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("BEGIN IMMEDIATE")

        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(option_positions)"
            )
        }

        if not columns:
            raise RuntimeError(
                "option_positions table not found; "
                "migration aborted"
            )

        if "stop_price" not in columns:
            connection.execute(
                "ALTER TABLE option_positions "
                "ADD COLUMN stop_price NUMERIC(12,4)"
            )

        if "close_reason" not in columns:
            connection.execute(
                "ALTER TABLE option_positions "
                "ADD COLUMN close_reason VARCHAR(20)"
            )

        if "option_symbol" not in columns:
            connection.execute(
                "ALTER TABLE option_positions "
                "ADD COLUMN option_symbol VARCHAR(32)"
    )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    migrate()
    print(
        "Stop fields migration completed "
        "(existing positions left unchanged)."
    )
