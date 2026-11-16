"""Create the independent, non-executable classification review table.

Run in a controlled deployment after confirming the existing classification
contract migration is installed. No existing tables or rows are modified.
"""

from sqlalchemy import inspect

from my_trading_simulator.database.models import ClassificationTradeReview
from my_trading_simulator.database.session import engine


def migrate(bind=engine) -> bool:
    inspector = inspect(bind)
    required = {"notification_classifications", "paper_accounts", "trade_ideas", "option_positions"}
    if not required.issubset(set(inspector.get_table_names())):
        raise RuntimeError("Required trading schema missing; migration refused")
    existed = "classification_trade_reviews" in inspector.get_table_names()
    ClassificationTradeReview.__table__.create(bind=bind, checkfirst=True)
    return not existed


if __name__ == "__main__":
    created = migrate()
    print("Trade idea review table:", "created" if created else "already present")
    print("Automated trading: DISABLED")
