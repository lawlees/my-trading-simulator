
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from schwab.auth import client_from_token_file


class SchwabMarketDataClient:
    """
    Read-only Schwab market-data client.

    This class fetches quotes and option chains.
    It does not submit trading orders.
    """

    def __init__(self):
        load_dotenv()

        app_key = os.getenv("SCHWAB_APP_KEY")
        app_secret = os.getenv("SCHWAB_APP_SECRET")

        if not app_key or not app_secret:
            raise RuntimeError(
                "Missing Schwab credentials in .env"
            )

        project_root = Path(__file__).resolve().parents[3]
        token_path = project_root / "schwab_token.json"

        if not token_path.exists():
            raise FileNotFoundError(
                f"Schwab OAuth token not found: {token_path}"
            )

        self.client = client_from_token_file(
            token_path=str(token_path),
            api_key=app_key,
            app_secret=app_secret,
        )

    def get_stock_quote(self, symbol: str) -> dict:
        """
        Fetch a stock or ETF quote from Schwab.
        """
        symbol = symbol.strip().upper()

        if symbol not in {"SPY", "QQQ", "IWM"}:
            raise ValueError(
                f"Unsupported symbol: {symbol}"
            )

        response = self.client.get_quote(symbol)
        response.raise_for_status()

        return response.json()

    def get_0dte_option_chain(
        self,
        symbol: str,
        trading_date: date | None = None,
        strike_count: int = 10,
    ) -> dict:
        """
        Fetch options expiring on the requested date.

        By default, uses today's New York date.
        """
        symbol = symbol.strip().upper()

        if symbol not in {"SPY", "QQQ", "IWM"}:
            raise ValueError(
                f"Unsupported symbol: {symbol}"
            )

        if trading_date is None:
            trading_date = datetime.now(
                ZoneInfo("America/New_York")
            ).date()

        response = self.client.get_option_chain(
            symbol,
            contract_type=self.client.Options.ContractType.ALL,
            from_date=trading_date,
            to_date=trading_date,
            strike_count=strike_count,
        )

        response.raise_for_status()

        return response.json()
