
import os

from dotenv import load_dotenv
from schwab.auth import client_from_token_file

load_dotenv()

client = client_from_token_file(
    token_path="schwab_token.json",
    api_key=os.environ["SCHWAB_APP_KEY"],
    app_secret=os.environ["SCHWAB_APP_SECRET"],
)

response = client.get_quote("SPY")

print("HTTP status:", response.status_code)

if response.status_code == 200:
    data = response.json()
    spy = data.get("SPY", {})
    quote = spy.get("quote", {})

    print("Symbol:", spy.get("symbol", "SPY"))
    print("Bid:", quote.get("bidPrice"))
    print("Ask:", quote.get("askPrice"))
    print("Last:", quote.get("lastPrice"))
    print("Quote time:", quote.get("quoteTime"))
else:
    print("Schwab API request failed.")
    print("Response:", response.text[:500])
