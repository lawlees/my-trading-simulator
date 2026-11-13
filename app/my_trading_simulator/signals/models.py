
from enum import Enum

from pydantic import BaseModel, Field


class SignalAction(str, Enum):
    BUY = "BUY"
    ADD = "ADD"
    PROFIT_TAKE = "PROFIT_TAKE"
    CLOSE = "CLOSE"
    IGNORE = "IGNORE"


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class TradingSignal(BaseModel):
    # Unique Discord message ID for duplicate detection.
    message_id: str = Field(min_length=1)

    # Original message from Casey.
    raw_message: str

    # Action determined from the message.
    action: SignalAction

    # SPY, QQQ, or IWM when identifiable.
    symbol: str | None = None

    # CALL or PUT when identifiable.
    option_type: OptionType | None = None

    # Whether the message is sufficiently clear.
    is_actionable: bool = False

    # Explanation for the decision.
    reason: str
