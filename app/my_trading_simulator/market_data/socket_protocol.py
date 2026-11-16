"""Strict request validation for the read-only market-data socket."""

from datetime import date

ALLOWED_SYMBOLS = frozenset({"SPY", "QQQ", "IWM"})
ALLOWED_OPERATIONS = frozenset({"stock_quote", "option_chain"})

SOCKET_PATH = (
    "/run/my-trading-simulator-market-data/schwab.sock"
)

MAX_REQUEST_BYTES = 4096
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class MarketDataRequestError(ValueError):
    """Invalid or unauthorized market-data request."""


def validate_market_data_request(request: object) -> dict:
    """Return a validated request or raise MarketDataRequestError."""

    if not isinstance(request, dict):
        raise MarketDataRequestError("Request must be an object")

    operation = request.get("operation")
    symbol = request.get("symbol")

    if operation not in ALLOWED_OPERATIONS:
        raise MarketDataRequestError("Unsupported operation")

    if type(symbol) is not str or symbol not in ALLOWED_SYMBOLS:
        raise MarketDataRequestError("Unsupported symbol")

    if operation == "stock_quote":
        if set(request) != {"operation", "symbol"}:
            raise MarketDataRequestError(
                "Unexpected stock quote parameters"
            )

        return {
            "operation": operation,
            "symbol": symbol,
        }

    if set(request) != {
        "operation",
        "symbol",
        "trading_date",
        "strike_count",
    }:
        raise MarketDataRequestError(
            "Invalid option chain parameters"
        )

    trading_date = request["trading_date"]
    strike_count = request["strike_count"]

    if type(trading_date) is not str:
        raise MarketDataRequestError("Invalid trading date")

    try:
        parsed_date = date.fromisoformat(trading_date)
    except ValueError:
        raise MarketDataRequestError(
            "Invalid trading date"
        ) from None

    if parsed_date.isoformat() != trading_date:
        raise MarketDataRequestError(
            "Trading date must use YYYY-MM-DD"
        )

    if type(strike_count) is not int or not 1 <= strike_count <= 25:
        raise MarketDataRequestError(
            "Strike count must be between 1 and 25"
        )

    return {
        "operation": operation,
        "symbol": symbol,
        "trading_date": trading_date,
        "strike_count": strike_count,
    }
