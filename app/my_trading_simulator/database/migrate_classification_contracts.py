"""Add optional explicit contract details to saved dry-run classifications.

Run separately during a controlled deployment, BEFORE updating the classifier.
No existing rows are removed or changed. Safe to rerun.
"""

from sqlalchemy import inspect

from my_trading_simulator.database.session import engine

TABLE_NAME = "notification_classifications"
COLUMNS = {
    "strike_price": "NUMERIC(12, 3)",
    "contract_symbol": "VARCHAR(32)",
}


def migrate(bind=engine) -> tuple[str, ...]:
    inspector = inspect(bind)
    if TABLE_NAME not in inspector.get_table_names():
        raise RuntimeError(
            "Classification table is missing; initialize existing schema first"
        )

    # SQLite requires each ALTER TABLE to occur under a write transaction.
    # BEGIN IMMEDIATE prevents concurrent migrations from racing the column checks.
    with bind.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            existing = {
                item[1] for item in connection.exec_driver_sql(
                    "PRAGMA table_info(notification_classifications)"
                )
            }
            added = []
            for name, definition in COLUMNS.items():
                if name not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {TABLE_NAME} ADD COLUMN {name} {definition}"
                    )
                    added.append(name)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return tuple(added)


if __name__ == "__main__":
    added = migrate()
    print("Classification contract migration complete; added:", added or "none")
