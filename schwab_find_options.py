
from decimal import Decimal

from my_trading_simulator.market_data.schwab_client import (
    SchwabMarketDataClient,
)


def main():
    client = SchwabMarketDataClient()

    data = client.get_0dte_option_chain(
        symbol="SPY",
        strike_count=25,
    )

    print("Underlying:", data.get("symbol"))
    print("Underlying price:", data.get("underlyingPrice"))

    target_min = Decimal("0.40")
    target_max = Decimal("0.50")

    matches = []
    total_contracts = 0

    for option_type, map_name in (
        ("CALL", "callExpDateMap"),
        ("PUT", "putExpDateMap"),
    ):
        for expiration, strikes in data.get(
            map_name, {}
        ).items():
            for strike, contracts in strikes.items():
                for option in contracts:
                    total_contracts += 1

                    ask = option.get("ask")
                    bid = option.get("bid")

                    if ask is None or bid is None:
                        continue

                    ask = Decimal(str(ask))
                    bid = Decimal(str(bid))

                    if target_min <= ask <= target_max:
                        matches.append(
                            (
                                option_type,
                                option.get("symbol"),
                                expiration,
                                strike,
                                bid,
                                ask,
                                option.get("totalVolume"),
                            )
                        )

    print("Total contracts returned:", total_contracts)
    print("Contracts priced $0.40–$0.50:", len(matches))

    for (
        option_type,
        symbol,
        expiration,
        strike,
        bid,
        ask,
        volume,
    ) in matches:
        print(
            option_type,
            symbol,
            "Expiration:", expiration,
            "Strike:", strike,
            "Bid:", bid,
            "Ask:", ask,
            "Volume:", volume,
        )


if __name__ == "__main__":
    main()
