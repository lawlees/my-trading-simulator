
from datetime import datetime
from zoneinfo import ZoneInfo

from my_trading_simulator.market_data.schwab_client import (
    SchwabMarketDataClient,
)


def main():
    client = SchwabMarketDataClient()

    trading_date = datetime.now(
        ZoneInfo("America/New_York")
    ).date()

    chain = client.get_0dte_option_chain(
        symbol="SPY",
        trading_date=trading_date,
        strike_count=5,
    )

    print("Trading date:", trading_date)

    for map_name in ("callExpDateMap", "putExpDateMap"):
        for expiration_key, strikes in chain.get(
            map_name, {}
        ).items():
            for contracts in strikes.values():
                for option in contracts:
                    print(
                        "\nContract:",
                        option.get("symbol"),
                    )

                    print("Timestamp-related fields:")

                    found = False

                    for key, value in option.items():
                        if any(
                            word in key.lower()
                            for word in (
                                "time",
                                "date",
                                "quote",
                                "trade",
                            )
                        ):
                            print(f"  {key}: {value}")
                            found = True

                    if not found:
                        print("  None found")

                    return


if __name__ == "__main__":
    main()
