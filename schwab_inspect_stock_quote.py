from pprint import pprint

from my_trading_simulator.market_data.schwab_client import (
    SchwabMarketDataClient,
)


def main():
    client = SchwabMarketDataClient()

    response = client.get_stock_quote("SPY")

    spy_data = response.get("SPY", {})
    quote = spy_data.get("quote", {})

    print("\nSPY quote fields:")
    pprint(sorted(quote.keys()))

    print("\nSelected quote values:")

    for field in (
        "bidPrice",
        "askPrice",
        "lastPrice",
        "quoteTime",
        "tradeTime",
    ):
        print(f"{field}: {quote.get(field)}")


if __name__ == "__main__":
    main()