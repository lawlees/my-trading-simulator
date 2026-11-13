
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from my_trading_simulator.database.models import DiscordMessage


@dataclass(frozen=True)
class MessageContext:
    discord_message_id: str
    message_text: str
    message_timestamp: datetime
    action: str | None
    trade_idea_id: int | None
    position_id: int | None


def get_recent_messages(
    session: Session,
    author_id: str,
    channel_id: str,
    limit: int = 10,
    before_timestamp: datetime | None = None,
) -> list[MessageContext]:
    """
    Retrieve recent messages for one author and channel.

    Results are returned in chronological order.
    """
    if limit < 1 or limit > 50:
        raise ValueError("limit must be between 1 and 50")

    query = (
        select(DiscordMessage)
        .where(DiscordMessage.author_id == author_id)
        .where(DiscordMessage.channel_id == channel_id)
    )

    if before_timestamp is not None:
        query = query.where(
            DiscordMessage.message_timestamp < before_timestamp
        )

    query = (
        query.order_by(
            DiscordMessage.message_timestamp.desc(),
            DiscordMessage.id.desc(),
        )
        .limit(limit)
    )

    messages = session.scalars(query).all()

    return [
        MessageContext(
            discord_message_id=message.discord_message_id,
            message_text=message.message_text,
            message_timestamp=message.message_timestamp,
            action=message.action,
            trade_idea_id=message.trade_idea_id,
            position_id=message.position_id,
        )
        for message in reversed(messages)
    ]
