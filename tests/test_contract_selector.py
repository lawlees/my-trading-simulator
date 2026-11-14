
from decimal import Decimal
from datetime import date

from my_trading_simulator.market_data.contract_selector import (
    find_contracts_by_premium,
)

from my_trading_simulator.market_data.contract_selector import (
    find_contracts_by_premium,
    find_contract_by_strike,
    find_contract_by_symbol,
)


def make_chain():
    return {
        "symbol": "SPY",
        "callExpDateMap": {
            "2026-11-12:0": {
                "760.0": [
                    {
                        "symbol": "SPY 261112C00760000",
                        "bid": 0.43,
                        "ask": 0.45,
                        "totalVolume": 100,
                    }
                ],
                "761.0": [
                    {
                        "symbol": "SPY 261112C00761000",
                        "bid": 0.20,
                        "ask": 0.22,
                        "totalVolume": 200,
                    }
                ],
            }
        },
        "putExpDateMap": {
            "2026-11-12:0": {
                "758.0": [
                    {
                        "symbol": "SPY 261112P00758000",
                        "bid": 0.45,
                        "ask": 0.48,
                        "totalVolume": 150,
                    }
                ]
            }
        },
    }


def test_finds_call_in_target_range():
    matches = find_contracts_by_premium(
        make_chain(),
        "CALL",
    )

    assert len(matches) == 1
    assert matches[0].symbol == "SPY 261112C00760000"
    assert matches[0].ask == Decimal("0.45")


def test_finds_put_in_target_range():
    matches = find_contracts_by_premium(
        make_chain(),
        "PUT",
    )

    assert len(matches) == 1
    assert matches[0].symbol == "SPY 261112P00758000"
    assert matches[0].ask == Decimal("0.48")


def test_does_not_mix_calls_and_puts():
    calls = find_contracts_by_premium(
        make_chain(),
        "CALL",
    )

    puts = find_contracts_by_premium(
        make_chain(),
        "PUT",
    )

    assert all(
        contract.option_type == "CALL"
        for contract in calls
    )

    assert all(
        contract.option_type == "PUT"
        for contract in puts
    )


def test_rejects_invalid_option_type():
    try:
        find_contracts_by_premium(
            make_chain(),
            "INVALID",
        )
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_excludes_contracts_outside_target_range():
    matches = find_contracts_by_premium(
        make_chain(),
        "CALL",
        target_min=Decimal("0.60"),
        target_max=Decimal("0.80"),
    )

    assert matches == []


def test_explicit_strike_takes_priority_over_premium():
    """
    Casey explicitly requests SPY 761 CALL.

    The simulator must select the 761 CALL
    even though its ask is outside the
    preferred $0.40-$0.50 range.
    """
    contract = find_contract_by_strike(
        chain=make_chain(),
        option_type="CALL",
        strike_price=Decimal("761"),
        expiration_date=date(2026, 11, 12),
    )

    assert contract is not None
    assert contract.symbol == "SPY 261112C00761000"
    assert contract.strike_price == Decimal("761")
    assert contract.ask == Decimal("0.22")



def test_fallback_only_selects_requested_expiration():
    """
    Fallback selection must never return
    contracts expiring on another date.
    """
    chain = make_chain()

    # Add a contract expiring tomorrow,
    # priced exactly at our target.
    chain["callExpDateMap"]["2026-11-13:1"] = {
        "762.0": [
            {
                "symbol": "SPY 261113C00762000",
                "bid": 0.44,
                "ask": 0.45,
                "totalVolume": 200,
            }
        ]
    }

    matches = find_contracts_by_premium(
        chain,
        "CALL",
        expiration_date=date(2026, 11, 12),
    )

    assert len(matches) == 1
    assert matches[0].symbol == "SPY 261112C00760000"
    assert matches[0].expiration_date == date(
        2026, 11, 12
    )


def test_schwab_quote_timestamp_is_preserved():
    chain = make_chain()

    expected_timestamp = 1794518100312

    chain["callExpDateMap"]["2026-11-12:0"]["760.0"][0][
        "quoteTimeInLong"
    ] = expected_timestamp

    matches = find_contracts_by_premium(
        chain=chain,
        option_type="CALL",
        expiration_date=date(2026, 11, 12),
    )

    assert len(matches) == 1
    assert matches[0].quote_timestamp_ms == expected_timestamp



def test_selects_exact_option_symbol():
    chain = make_chain()

    contract = find_contract_by_symbol(
        chain=chain,
        contract_symbol="SPY 261112C00761000",
        expiration_date=date(2026, 11, 12),
    )

    assert contract is not None
    assert contract.symbol == "SPY 261112C00761000"
    assert contract.option_type == "CALL"
    assert contract.strike_price == Decimal("761")
    assert contract.expiration_date == date(2026, 11, 12)
    assert contract.ask == Decimal("0.22")
