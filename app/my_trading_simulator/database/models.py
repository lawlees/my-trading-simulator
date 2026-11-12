from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    pass


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )

    initial_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )

    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

class AccountTransaction(Base):
    __tablename__ = "account_transactions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id"),
        nullable=False,
        index=True,
    )

    transaction_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    account: Mapped["PaperAccount"] = relationship()

    