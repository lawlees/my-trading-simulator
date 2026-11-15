
"""Read-only Schwab market data with secure OAuth token storage.

Local development:
    Use the existing project-root schwab_token.json.

AWS Schwab worker:
    Require the dedicated schwab-worker Linux account.
    Use a protected local OAuth token file owned by that account.
    Routine token refreshes do not write to AWS Secrets Manager.

AWS Secrets Manager:
    Retained for future explicit OAuth backup/recovery operations.

No brokerage order submission is implemented here.
"""

import json
import os
import pwd
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from schwab.auth import (
    client_from_access_functions,
    client_from_token_file,
)

from my_trading_simulator.observability.performance import timed
from my_trading_simulator.secrets_manager import get_credential
from my_trading_simulator.market_data.schwab_local_token_store import (
    SchwabLocalTokenStore,
)


SCHWAB_TOKEN_SECRET_NAME = "my-trading-simulator/schwab-oauth-tokens"
AWS_REGION = "us-east-2"
AWS_PROFILE_NAME = "my-trading-simulator-schwab"

AWS_SCHWAB_TOKEN_PATH = Path(
    "/var/lib/schwab-worker/schwab_token.json"
)


def _validate_token(token: dict) -> None:
    """Validate schwab-py's OAuth token format without exposing secrets."""
    if (
        not isinstance(token, dict)
        or not isinstance(token.get("token"), dict)
        or not isinstance(
            token.get("creation_timestamp"),
            (int, float),
        )
        or not token["token"].get("access_token")
        or not token["token"].get("refresh_token")
    ):
        raise ValueError(
            "Invalid or uninitialized Schwab OAuth token"
        )


def require_schwab_worker_identity() -> None:
    """Require AWS Schwab access to run under the dedicated Linux user.

    Resolves the account UID dynamically instead of hardcoding it.
    This check applies to AWS mode only.
    """
    try:
        expected_uid = pwd.getpwnam("schwab-worker").pw_uid
    except KeyError:
        raise RuntimeError(
            "Dedicated schwab-worker Linux account not found"
        ) from None

    if os.geteuid() != expected_uid:
        raise RuntimeError(
            "AWS Schwab access requires the schwab-worker Linux account"
        )


class SchwabOAuthSecretStore:
    """Explicit AWS Secrets Manager OAuth backup/recovery storage.

    Uses the dedicated Schwab IAM Roles Anywhere profile.

    This class is retained for future controlled backup and recovery.
    It is NOT used for routine access-token refreshes.

    Backup synchronization, conflict detection, and recovery policy
    are not yet implemented. Do not use this class to automatically
    overwrite an existing OAuth secret.
    """

    def __init__(self):
        import boto3

        session = boto3.Session(
            profile_name=AWS_PROFILE_NAME,
            region_name=AWS_REGION,
        )

        self.client = session.client("secretsmanager")

    def read_token(self) -> dict:
        """Read the complete OAuth token object from Secrets Manager."""
        response = self.client.get_secret_value(
            SecretId=SCHWAB_TOKEN_SECRET_NAME,
        )

        try:
            token = json.loads(response["SecretString"])
            _validate_token(token)
        except (
            KeyError,
            TypeError,
            json.JSONDecodeError,
            ValueError,
        ):
            raise RuntimeError(
                "Schwab OAuth secret is not initialized "
                "with a valid token"
            ) from None

        return token

    def write_token(
        self,
        token: dict,
        *args,
        **kwargs,
    ) -> None:
        """Write a complete OAuth token to Secrets Manager.

        Intended only for explicit, controlled backup operations.
        Never call this on every access-token refresh.
        """
        _validate_token(token)

        self.client.put_secret_value(
            SecretId=SCHWAB_TOKEN_SECRET_NAME,
            SecretString=json.dumps(token),
        )


class SchwabMarketDataClient:
    """Read-only Schwab market-data client.

    Supported underlying symbols:
        SPY, QQQ, IWM

    Local OAuth:
        Project-root schwab_token.json.

    AWS OAuth:
        /var/lib/schwab-worker/schwab_token.json.

    AWS initialization requires the dedicated Linux account and
    configured Schwab AWS profile.

    The caller must acquire the exclusive Schwab worker lock before
    creating this client and hold it for its entire lifetime.
    """

    def __init__(self):
        source = os.getenv(
            "MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE",
            "local",
        ).strip().lower()

        if source == "aws":
            require_schwab_worker_identity()

            configured_profile = os.getenv(
                "MY_TRADING_SIMULATOR_AWS_PROFILE",
            )

            if configured_profile != AWS_PROFILE_NAME:
                raise RuntimeError(
                    "AWS Schwab market data requires the "
                    "dedicated Schwab worker IAM profile"
                )

            app_key = get_credential("SCHWAB_APP_KEY")
            app_secret = get_credential("SCHWAB_APP_SECRET")

            if not AWS_SCHWAB_TOKEN_PATH.is_file():
                raise RuntimeError(
                    "Schwab worker OAuth token file is not "
                    "initialized. Market-data access "
                    "remains disabled."
                )

            self.token_store = SchwabLocalTokenStore(
                AWS_SCHWAB_TOKEN_PATH
            )

            # Validate existing file permissions and token structure
            # before allowing the Schwab library to initialize.
            self.token_store.read_token()

            self.client = client_from_access_functions(
                api_key=app_key,
                app_secret=app_secret,
                token_read_func=self.token_store.read_token,
                token_write_func=self.token_store.write_token,
            )

        elif source == "local":
            app_key = get_credential("SCHWAB_APP_KEY")
            app_secret = get_credential("SCHWAB_APP_SECRET")

            project_root = Path(__file__).resolve().parents[3]
            token_path = project_root / "schwab_token.json"

            if not token_path.is_file():
                raise FileNotFoundError(
                    f"Schwab OAuth token not found: {token_path}"
                )

            self.client = client_from_token_file(
                token_path=str(token_path),
                api_key=app_key,
                app_secret=app_secret,
            )

        else:
            raise ValueError(
                f"Invalid credential source: {source}"
            )

    @timed("schwab_stock_quote")
    def get_stock_quote(self, symbol: str) -> dict:
        """Fetch a stock or ETF quote for SPY, QQQ, or IWM."""
        symbol = symbol.strip().upper()

        if symbol not in {"SPY", "QQQ", "IWM"}:
            raise ValueError(
                f"Unsupported symbol: {symbol}"
            )

        response = self.client.get_quote(symbol)
        response.raise_for_status()

        return response.json()

    @timed("schwab_option_quote")
    def get_option_quote(self, option_symbol: str) -> dict:
        """Fetch the quote for one exact option contract.

        The returned quote must still undergo independent
        validation before paper-trading decisions.
        """
        if not isinstance(option_symbol, str):
            raise ValueError(
                "Option symbol must be a string"
            )

        symbol = option_symbol.strip()

        if not symbol:
            raise ValueError(
                "Option symbol cannot be empty"
            )

        response = self.client.get_quotes([symbol])
        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict) or not data:
            raise ValueError(
                "Schwab returned no option quote"
            )

        if symbol not in data:
            raise ValueError(
                "Schwab did not return the requested "
                f"contract: {symbol}"
            )

        return data[symbol]

    @timed("schwab_option_chain")
    def get_0dte_option_chain(
        self,
        symbol: str,
        trading_date: date | None = None,
        strike_count: int = 10,
    ) -> dict:
        """Fetch the option chain for a specific trading date."""
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
