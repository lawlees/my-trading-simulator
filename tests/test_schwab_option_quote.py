
from unittest.mock import MagicMock

import pytest

from my_trading_simulator.market_data.schwab_client import (
    SchwabMarketDataClient,
)


def make_client(response_data):
    """Create a Schwab client without real authentication."""
    client = SchwabMarketDataClient.__new__(
        SchwabMarketDataClient
    )

    client.client = MagicMock()
    client.client.get_quotes.return_value.json.return_value = (
        response_data
    )

    return client


def test_exact_option_quote():
    option_symbol = "SPY   261113C00600000"

    client = make_client({
        option_symbol: {
            "quote": {
                "bidPrice": 0.40,
                "askPrice": 0.42,
            }
        }
    })

    result = client.get_option_quote(option_symbol)

    assert result["quote"]["bidPrice"] == 0.40

    client.client.get_quotes.assert_called_once_with(
        [option_symbol]
    )


def test_missing_option_quote_rejected():
    client = make_client({})

    with pytest.raises(
        ValueError,
        match="no option quote",
    ):
        client.get_option_quote(
            "SPY   261113C00600000"
        )


def test_wrong_contract_quote_rejected():
    client = make_client({
        "QQQ   261113C00600000": {
            "quote": {
                "bidPrice": 0.40,
                "askPrice": 0.42,
            }
        }
    })

    with pytest.raises(
        ValueError,
        match="did not return the requested contract",
    ):
        client.get_option_quote(
            "SPY   261113C00600000"
        )


def test_empty_symbol_rejected():
    client = make_client({})

    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        client.get_option_quote("   ")
