
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from schwab.auth import client_from_token_file


def main():
    # Load Schwab credentials from .env
    load_dotenv()

    app_key = os.environ["SCHWAB_APP_KEY"]
    app_secret = os.environ["SCHWAB_APP_SECRET"]

    # Reuse the OAuth token created earlier
    client = client_from_token_file(
        token_path="schwab_token.json",
        api_key=app_key,
        app_secret=app_secret,
    )

    # Use New York date for US options trading
    today = datetime.now(
        ZoneInfo("America/New_York")
    ).date()

    print("Connecting to Schwab Market Data API...")
    print("Symbol: SPY")
    print("Requested expiration:", today)

    # Request only options expiring today (0DTE)
    response = client.get_option_chain(
        "SPY",
        contract_type=client.Options.ContractType.ALL,
        from_date=today,
        to_date=today,
        strike_count=5,
    )

    print("HTTP status:", response.status_code)

    if response.status_code != 200:
        print("Schwab API request failed.")
        print("Response:", response.text[:500])
        return

    data = response.json()

    print("Underlying:", data.get("symbol"))
    print("Underlying price:", data.get("underlyingPrice"))
    print("Chain status:", data.get("status"))

    contracts_found = 0

    # Schwab groups contracts by expiration and strike
    for side in ("callExpDateMap", "putExpDateMap"):
        print("\n" + side)

        expiration_map = data.get(side, {})

        for expiration, strikes in expiration_map.items():
            for strike, contracts in strikes.items():
                for option in contracts:
                    print(
                        "Symbol:", option.get("symbol"),
                        "| Exp:", expiration,
                        "| Strike:", strike,
                        "| Bid:", option.get("bid"),
                        "| Ask:", option.get("ask"),
                        "| Volume:", option.get("totalVolume"),
                    )

                    contracts_found += 1

    print("\nTotal contracts:", contracts_found)

    if contracts_found == 0:
        print(
            "No options found expiring today. "
            "This may happen on non-trading days "
            "or when no contracts expire today."
        )


if __name__ == "__main__":
    main()
