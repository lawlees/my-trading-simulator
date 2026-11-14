
from datetime import date, datetime
from decimal import Decimal

from my_trading_simulator.market_data.contract_selector import (
    OptionContract,
    find_contract_by_strike,
    find_contract_by_symbol,
    find_contracts_by_premium,
)
from my_trading_simulator.market_data.quote_validator import (
    validate_contract_for_paper_trade,
)
from my_trading_simulator.market_data.premium_safety import (
    validate_contract_premium,
)


def find_valid_fallback_contract(
    chain: dict,
    option_type: str,
    trading_date: date,
    now: datetime | None = None,
) -> OptionContract | None:
    """
    Find a fallback 0DTE contract.

    Requirements:
    - Correct option type
    - Expiration matches trading date
    - Premium passes configured fallback limits
    - Quote is fresh
    - Bid/ask spread is acceptable

    Returns None if no contract passes validation.
    """

    candidates = find_contracts_by_premium(
        chain=chain,
        option_type=option_type,
        expiration_date=trading_date,
    )

    for contract in candidates:
        premium_valid, _ = validate_contract_premium(
            ask=contract.ask,
            is_explicit=False,
        )

        if not premium_valid:
            continue

        quote_valid, _ = validate_contract_for_paper_trade(
            contract=contract,
            trading_date=trading_date,
            now=now,
        )

        if quote_valid:
            return contract

    return None


def find_valid_explicit_contract(
    chain: dict,
    option_type: str,
    strike_price: Decimal,
    trading_date: date,
    now: datetime | None = None,
) -> OptionContract | None:
    """
    Find Casey's exact requested strike and option type.

    Requirements:
    - Exact strike and option type
    - Expiration matches trading date
    - Premium passes configured explicit limits
    - Quote is fresh
    - Bid/ask spread is acceptable

    Never substitute a different strike.
    """

    contract = find_contract_by_strike(
        chain=chain,
        option_type=option_type,
        strike_price=strike_price,
        expiration_date=trading_date,
    )

    if contract is None:
        return None

    premium_valid, _ = validate_contract_premium(
        ask=contract.ask,
        is_explicit=True,
    )

    if not premium_valid:
        return None

    quote_valid, _ = validate_contract_for_paper_trade(
        contract=contract,
        trading_date=trading_date,
        now=now,
    )

    if not quote_valid:
        return None

    return contract


def find_valid_contract_by_symbol(
    chain: dict,
    contract_symbol: str,
    trading_date: date,
    now: datetime | None = None,
) -> OptionContract | None:
    """
    Find Casey's exact option contract by symbol.

    Requirements:
    - Exact contract symbol
    - Expiration matches trading date
    - Premium passes configured explicit limits
    - Quote is fresh
    - Bid/ask spread is acceptable

    Never substitute a different contract.
    """

    contract = find_contract_by_symbol(
        chain=chain,
        contract_symbol=contract_symbol,
        expiration_date=trading_date,
    )

    if contract is None:
        return None

    premium_valid, _ = validate_contract_premium(
        ask=contract.ask,
        is_explicit=True,
    )

    if not premium_valid:
        return None

    quote_valid, _ = validate_contract_for_paper_trade(
        contract=contract,
        trading_date=trading_date,
        now=now,
    )

    if not quote_valid:
        return None

    return contract
