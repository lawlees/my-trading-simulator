
from my_trading_simulator.signals.llm_parser import (
    parse_discord_message,
)


test_messages = [
    "Taking SPY calls here",
    "Buying QQQ puts now",
    "Taking some profits on SPY",
    "I'm fully out of QQQ",
    "Nice! 13ema held like a champ",
    "Waiting to see how we react to support before cutting runners on QQQ",
    "Now every 15 minute candle has brought a lower low",
    "I'm out of the rest",
]


for index, message in enumerate(test_messages, start=1):
    signal = parse_discord_message(
        message_id=f"test-{index:03d}",
        message_text=message,
    )

    print(f"\nMessage: {message}")
    print(f"Action: {signal.action.value}")
    print(f"Symbol: {signal.symbol}")
    print(f"Option type: {signal.option_type}")
    print(f"Actionable: {signal.is_actionable}")
    print(f"Reason: {signal.reason}")
    print("-" * 60)
