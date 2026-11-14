
import time
from statistics import mean

from my_trading_simulator.market_data.schwab_client import (
    SchwabMarketDataClient,
)
from my_trading_simulator.market_data.stock_quote_validator import (
    validate_stock_quote,
)


def main():
    client = SchwabMarketDataClient()

    symbol = "SPY"
    durations_ms = []

    print(f"\nTesting Schwab quote latency for {symbol}\n")

    for attempt in range(1, 6):
        start = time.perf_counter()

        try:
            response = client.get_stock_quote(symbol)
        except Exception as exc:
            elapsed_ms = (
                time.perf_counter() - start
            ) * 1000

            print(
                f"Request {attempt}: FAILED "
                f"after {elapsed_ms:.2f} ms "
                f"({type(exc).__name__})"
            )
            continue

        elapsed_ms = (
            time.perf_counter() - start
        ) * 1000

        durations_ms.append(elapsed_ms)

        midpoint, reason = validate_stock_quote(
            response=response,
            symbol=symbol,
        )

        freshness = (
            "VALID"
            if midpoint is not None
            else f"INVALID: {reason}"
        )

        print(
            f"Request {attempt}: "
            f"{elapsed_ms:.2f} ms | "
            f"Quote: {freshness}"
        )

        time.sleep(1)

    if durations_ms:
        print("\nLatency summary:")
        print(f"Minimum: {min(durations_ms):.2f} ms")
        print(f"Average: {mean(durations_ms):.2f} ms")
        print(f"Maximum: {max(durations_ms):.2f} ms")


if __name__ == "__main__":
    main()
