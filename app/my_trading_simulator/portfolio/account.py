from sqlalchemy import select

from my_trading_simulator.config.settings import settings
from my_trading_simulator.database.models import PaperAccount
from my_trading_simulator.database.session import SessionLocal

from decimal import Decimal
from sqlalchemy import update

from my_trading_simulator.database.models import AccountTransaction


def get_or_create_account() -> PaperAccount:
    with SessionLocal.begin() as session:
        account = session.scalar(
            select(PaperAccount).where(
                PaperAccount.name == "Main Paper Account"
            )
        )

        if account is None:
            account = PaperAccount(
                name="Main Paper Account",
                initial_balance=settings.starting_balance,
                cash_balance=settings.starting_balance,
            )
            session.add(account)
            session.flush()

            print("New paper account created.")
        else:
            print("Existing paper account loaded.")

        session.expunge(account)
        return account
    
def record_cash_transaction(
    account_id: int,
    transaction_type: str,
    amount: Decimal,
    description: str,
) -> Decimal:
    allowed_types = {"DEPOSIT", "WITHDRAWAL"}

    if transaction_type not in allowed_types:
        raise ValueError(f"Unsupported transaction type: {transaction_type}")

    if not amount.is_finite() or amount == 0:
        raise ValueError("Transaction amount must be finite and nonzero")

    if amount.as_tuple().exponent < -2:
        raise ValueError("Transaction amount cannot exceed two decimal places")

    if transaction_type == "DEPOSIT" and amount < 0:
        raise ValueError("Deposit amount must be positive")

    if transaction_type == "WITHDRAWAL" and amount > 0:
        raise ValueError("Withdrawal amount must be negative")

    with SessionLocal.begin() as session:
        # Update the balance without allowing negative cash.
        result = session.execute(
            update(PaperAccount)
            .where(PaperAccount.id == account_id)
            .where(PaperAccount.cash_balance + amount >= 0)
            .values(cash_balance=PaperAccount.cash_balance + amount)
        )

        if result.rowcount != 1:
            raise ValueError("Account not found or insufficient cash")

        session.add(
            AccountTransaction(
                account_id=account_id,
                transaction_type=transaction_type,
                amount=amount,
                description=description,
            )
        )

        new_balance = session.scalar(
            select(PaperAccount.cash_balance).where(
                PaperAccount.id == account_id
            )
        )

        return new_balance