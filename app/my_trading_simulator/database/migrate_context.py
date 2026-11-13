
from sqlalchemy import inspect, text

from my_trading_simulator.database.models import (
    Base,
    DiscordMessage,
    TradeIdea,
)
from my_trading_simulator.database.session import engine


def migrate():
    print("Starting context database migration...")

    # Create new tables if they do not already exist.
    Base.metadata.create_all(
        bind=engine,
        tables=[
            TradeIdea.__table__,
            DiscordMessage.__table__,
        ],
    )

    inspector = inspect(engine)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("option_positions")
    }

    with engine.begin() as connection:
        if "trade_idea_id" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE option_positions "
                    "ADD COLUMN trade_idea_id INTEGER "
                    "REFERENCES trade_ideas(id)"
                )
            )
            print("Added option_positions.trade_idea_id")
        else:
            print("trade_idea_id already exists")

        if "entry_type" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE option_positions "
                    "ADD COLUMN entry_type VARCHAR(20) "
                    "NOT NULL DEFAULT 'INITIAL'"
                )
            )
            print("Added option_positions.entry_type")
        else:
            print("entry_type already exists")

    print("Context database migration completed.")


if __name__ == "__main__":
    migrate()
