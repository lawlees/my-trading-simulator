"""Read-only request dispatch for the Schwab market-data worker."""

from datetime import date

from my_trading_simulator.market_data.socket_protocol import (
    validate_market_data_request,
)


def dispatch_market_data_request(client, request: object) -> dict:
    """
    Validate and dispatch a supported market-data request.

    The caller must hold the canonical Schwab worker lock
    before initializing the client and invoking this function.

    No brokerage order operations are supported.
    """
    validated = validate_market_data_request(request)

    operation = validated["operation"]
    symbol = validated["symbol"]

    if operation == "stock_quote":
        return client.get_stock_quote(symbol)

    if operation == "option_chain":
        return client.get_0dte_option_chain(
            symbol=symbol,
            trading_date=date.fromisoformat(
                validated["trading_date"]
            ),
            strike_count=validated["strike_count"],
        )

    raise RuntimeError("Unreachable market-data operation")
