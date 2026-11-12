from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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

class OptionPosition(Base):
    __tablename__ = "option_positions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id"),
        nullable=False,
        index=True,
    )

    symbol: Mapped[str] = mapped_column(
        String(10), nullable=False
    )

    option_type: Mapped[str] = mapped_column(
        String(4), nullable=False
    )

    strike_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False
    )

    expiration_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    remaining_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OPEN"
    )

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


    profit_take_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    runner_stop_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4),
        nullable=True,
    )


    profit_take_status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        nullable=False,
    )



class TradeFill(Base):
    __tablename__ = "trade_fills"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    position_id: Mapped[int] = mapped_column(
        ForeignKey("option_positions.id"),
        nullable=False,
        index=True,
    )

    side: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
    )

    commission: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    filled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )