
from datetime import date, datetime, timezone
from decimal import Decimal

from my_trading_simulator.market_data.market_data_coordinator import (
    MarketDataCoordinator,
)


TRADING_DATE = date(2026, 11, 12)

NOW = datetime(
    2026, 11, 12, 15, 0, 0,
    tzinfo=timezone.utc,
)


def timestamp_ms(dt):
    return int(dt.timestamp() * 1000)


class FakeSchwabClient:
    """
    Fake market-data client for testing.

    Makes no real Schwab API calls.
    """

    def __init__(self):
        self.chain_requests = 0
        self.quote_requests = 0

    def get_0dte_option_chain(
        self,
        symbol,
        trading_date=None,
        strike_count=25,
    ):
        self.chain_requests += 1

        return {
            "symbol": symbol,
            "callExpDateMap": {
                "2026-11-12:0": {
                    "760.0": [
                        {
                            "symbol": "SPY 261112C00760000",
                            "bid": 0.43,
                            "ask": 0.45,
                            "totalVolume": 100,
                            "quoteTimeInLong": timestamp_ms(NOW),
                        }
                    ],
                    "761.0": [
                        {
                            "symbol": "SPY 261112C00761000",
                            "bid": 0.44,
                            "ask": 0.48,
                            "totalVolume": 100,
                            "quoteTimeInLong": timestamp_ms(NOW),
                        }
                    ],
                }
            },
            "putExpDateMap": {},
        }

    def get_stock_quote(self, symbol):
        self.quote_requests += 1

        return {
            symbol: {
                "quote": {
                    "bidPrice": 759,
                    "askPrice": 761,
                    "quoteTime": timestamp_ms(NOW),
                }
            }
        }


def test_explicit_strike_selection():
    fake_client = FakeSchwabClient()

    coordinator = MarketDataCoordinator(
        market_data_client=fake_client
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="CALL",
        trading_date=TRADING_DATE,
        strike_price=Decimal("761"),
        now=NOW,
    )

    assert contract is not None
    assert contract.symbol == "SPY 261112C00761000"
    assert fake_client.chain_requests == 1
    assert fake_client.quote_requests == 1


def test_full_symbol_selection():
    fake_client = FakeSchwabClient()

    coordinator = MarketDataCoordinator(
        market_data_client=fake_client
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="CALL",
        trading_date=TRADING_DATE,
        contract_symbol="SPY 261112C00761000",
        now=NOW,
    )

    assert contract is not None
    assert contract.symbol == "SPY 261112C00761000"
    assert fake_client.chain_requests == 1
    assert fake_client.quote_requests == 1


def test_fallback_selection():
    fake_client = FakeSchwabClient()

    coordinator = MarketDataCoordinator(
        market_data_client=fake_client
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is not None
    assert contract.option_type == "CALL"
    assert Decimal("0.40") <= contract.ask <= Decimal("0.50")
    assert fake_client.chain_requests == 1
    assert fake_client.quote_requests == 1


def test_rejects_conflicting_explicit_contract_inputs():
    fake_client = FakeSchwabClient()

    coordinator = MarketDataCoordinator(
        market_data_client=fake_client
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="CALL",
        trading_date=TRADING_DATE,
        strike_price=Decimal("761"),
        contract_symbol="SPY 261112C00761000",
        now=NOW,
    )

    assert contract is None
    assert fake_client.chain_requests == 0
    assert fake_client.quote_requests == 0


def test_rejects_unsupported_symbol():
    fake_client = FakeSchwabClient()

    coordinator = MarketDataCoordinator(
        market_data_client=fake_client
    )

    contract = coordinator.select_contract(
        symbol="AAPL",
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is None
    assert fake_client.chain_requests == 0


def test_rejects_unsupported_option_type():
    fake_client = FakeSchwabClient()

    coordinator = MarketDataCoordinator(
        market_data_client=fake_client
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="INVALID",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is None
    assert fake_client.chain_requests == 0


def test_rejects_stock_quote_api_failure():
    class FailingQuoteClient(FakeSchwabClient):
        def get_stock_quote(self, symbol):
            raise RuntimeError("Simulated Schwab API failure")

    coordinator = MarketDataCoordinator(
        market_data_client=FailingQuoteClient()
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="CALL",
        trading_date=TRADING_DATE,
        strike_price=Decimal("761"),
        now=NOW,
    )

    assert contract is None


def test_rejects_option_chain_api_failure():
    class FailingChainClient(FakeSchwabClient):
        def get_0dte_option_chain(
            self,
            symbol,
            trading_date=None,
            strike_count=25,
        ):
            raise RuntimeError("Simulated option-chain failure")

    coordinator = MarketDataCoordinator(
        market_data_client=FailingChainClient()
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is None

  
def test_rejects_mismatched_contract_symbol():
    """
    Reject a fallback contract when the OCC symbol
    contains a different underlying than requested.

    The fake chain contains only one candidate,
    deliberately labeled QQQ instead of SPY.
    """

    class MismatchedClient(FakeSchwabClient):
        def get_0dte_option_chain(
            self,
            symbol,
            trading_date=None,
            strike_count=25,
        ):
            chain = super().get_0dte_option_chain(
                symbol,
                trading_date,
                strike_count,
            )

            contracts = chain["callExpDateMap"][
                "2026-11-12:0"
            ]

            # Remove the otherwise-valid SPY 760 CALL.
            contracts.pop("760.0")

            # Keep only the 761 strike candidate,
            # but change its contract symbol to QQQ.
            contracts["761.0"][0][
                "symbol"
            ] = "QQQ 261112C00761000"

            return chain

    coordinator = MarketDataCoordinator(
        market_data_client=MismatchedClient()
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is None

def test_fallback_rejects_unsafe_strike():
    """
    Reject a fallback contract when its strike
    is more than 2% from the underlying price.
    """

    class UnsafeFallbackClient(FakeSchwabClient):
        def get_stock_quote(self, symbol):
            self.quote_requests += 1

            # SPY is trading around $650.
            # Available fallback strikes are 760 and 761.
            return {
                symbol: {
                    "quote": {
                        "bidPrice": 649,
                        "askPrice": 651,
                        "quoteTime": timestamp_ms(NOW),
                    }
                }
            }

    fake_client = UnsafeFallbackClient()

    coordinator = MarketDataCoordinator(
        market_data_client=fake_client,
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is None
    assert fake_client.quote_requests == 1


def test_fallback_skips_unsafe_strike_and_selects_valid_candidate():
    """
    When the first fallback contract fails strike safety,
    the coordinator should try the next candidate.

    Casey has not specified an exact contract,
    so fallback selection is permitted.
    """

    class MixedFallbackClient(FakeSchwabClient):
        def get_0dte_option_chain(
            self,
            symbol,
            trading_date=None,
            strike_count=25,
        ):
            chain = super().get_0dte_option_chain(
                symbol,
                trading_date,
                strike_count,
            )

            contracts = chain["callExpDateMap"][
                "2026-11-12:0"
            ]

            # First candidate: strike 700, too far
            # from the underlying price of $760.
            contracts.pop("760.0")

            contracts["700.0"] = [
                {
                    "symbol": "SPY 261112C00700000",
                    "bid": 0.43,
                    "ask": 0.45,
                    "totalVolume": 100,
                    "quoteTimeInLong": timestamp_ms(NOW),
                }
            ]

            # Second candidate remains 761 CALL,
            # which is within the 2% limit.
            return chain

    fake_client = MixedFallbackClient()

    coordinator = MarketDataCoordinator(
        market_data_client=fake_client,
    )

    contract = coordinator.select_contract(
        symbol="SPY",
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is not None
    assert contract.symbol == "SPY 261112C00761000"
    assert fake_client.chain_requests == 1
    assert fake_client.quote_requests == 1
