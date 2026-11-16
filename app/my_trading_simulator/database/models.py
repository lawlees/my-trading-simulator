from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import Text

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

    option_symbol: Mapped[str | None] = mapped_column(
    String(32),
    nullable=True,
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

    # Initial option-premium stop, persisted across restarts.
    stop_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )

    close_reason: Mapped[str | None] = mapped_column(
        String(20), nullable=True
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


    trade_idea_id: Mapped[int | None] = mapped_column(
        ForeignKey("trade_ideas.id"),
        nullable=True,
    )

    entry_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="INITIAL",
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


class TradeIdea(Base):
    __tablename__ = "trade_ideas"

    id: Mapped[int] = mapped_column(primary_key=True)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id"),
        nullable=False,
    )

    symbol: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    option_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    size_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="NORMAL",
    )

    initial_allocation: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    initial_risk_limit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    additions_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class DiscordMessage(Base):
    __tablename__ = "discord_messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    discord_message_id: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
    )

    author_id: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    channel_id: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    message_text: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    message_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    action: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    is_actionable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    trade_idea_id: Mapped[int | None] = mapped_column(
        ForeignKey("trade_ideas.id"),
        nullable=True,
    )

    position_id: Mapped[int | None] = mapped_column(
        ForeignKey("option_positions.id"),
        nullable=True,
    )

    processing_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="RECEIVED",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )



class TradeEvent(Base):
    """
    Durable trading-event and Discord notification outbox.

    Trading activity is committed to SQLite first.
    A separate publisher delivers pending events to Discord.

    The publisher must never execute or repeat a trade.
    """

    __tablename__ = "trade_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_accounts.id"),
        nullable=True,
        index=True,
    )

    position_id: Mapped[int | None] = mapped_column(
        ForeignKey("option_positions.id"),
        nullable=True,
        index=True,
    )

    message: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
    )

    payload: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="{}",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    delivery_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        index=True,
    )

    delivery_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    discord_message_id: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    account: Mapped["PaperAccount | None"] = relationship()

    position: Mapped["OptionPosition | None"] = relationship()


class IncomingNotification(Base):
    """
    Stores incoming trading-related notifications.

    Sources:
      - IPHONE_NOTIFICATION
      - MANUAL_DISCORD
      - MANUAL_ENTRY

    This is an inbox only.
    Receiving a notification does NOT execute a trade.
    """

    __tablename__ = "incoming_notifications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    source_message_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Unique identifier assigned during ingestion.
    # Prevents a repeated request from creating another record.
    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    message_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    processing_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="RECEIVED",
        index=True,
    )

    processing_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

class NotificationClassification(Base):
    """Dry-run-only classification, separate from authenticated inbox and trading records."""

    __tablename__ = "notification_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("incoming_notifications.id"), unique=True, nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(10), nullable=True)
    option_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Casey's explicit instruction; NULL means no explicit contract supplied.
    strike_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    contract_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parser_is_actionable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    execution_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    model_message_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
