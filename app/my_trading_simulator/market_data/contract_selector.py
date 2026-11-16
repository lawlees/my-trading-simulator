"""Read-only parsing/selection of Schwab option-chain contracts.

Malformed individual quote entries fail closed without invalidating an otherwise
usable chain. This module NEVER authorizes an order or a paper fill.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    underlying_symbol: str
    option_type: str
    expiration_date: date
    strike_price: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    quote_timestamp_ms: int | None = None


def _map_name(option_type: str) -> str:
    if not isinstance(option_type, str):
        raise ValueError("option_type must be CALL or PUT")
    option_type = option_type.strip().upper()
    if option_type not in {"CALL", "PUT"}:
        raise ValueError("option_type must be CALL or PUT")
    return "callExpDateMap" if option_type == "CALL" else "putExpDateMap"


def _positive_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _nonnegative_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_contract(
    chain: dict, option_type: str, expiration: date, strike: object, option: object
) -> OptionContract | None:
    if not isinstance(option, dict):
        return None
    strike_price = _positive_decimal(strike)
    bid = _nonnegative_decimal(option.get("bid"))
    ask = _positive_decimal(option.get("ask"))
    contract_symbol = option.get("symbol")
    underlying = chain.get("symbol")
    if (
        strike_price is None or bid is None or ask is None or bid > ask
        or not isinstance(contract_symbol, str) or not contract_symbol.strip()
        or not isinstance(underlying, str) or not underlying.strip()
    ):
        return None
    raw_volume = option.get("totalVolume")
    try:
        volume = int(raw_volume) if raw_volume is not None else 0
        if isinstance(raw_volume, bool) or volume < 0:
            return None
    except (ValueError, TypeError, OverflowError):
        return None
    return OptionContract(
        symbol=contract_symbol,
        underlying_symbol=underlying,
        option_type=option_type,
        expiration_date=expiration,
        strike_price=strike_price,
        bid=bid,
        ask=ask,
        volume=volume,
        quote_timestamp_ms=option.get("quoteTimeInLong"),
    )


def _iter_contracts(chain: dict, option_type: str, expiration_date: date | None):
    map_name = _map_name(option_type)
    if not isinstance(chain, dict):
        return
    expiration_map = chain.get(map_name)
    if not isinstance(expiration_map, dict):
        return
    for expiration_key, strikes in expiration_map.items():
        try:
            actual_expiration = date.fromisoformat(str(expiration_key).split(":", 1)[0])
        except ValueError:
            continue
        if expiration_date is not None and actual_expiration != expiration_date:
            continue
        if not isinstance(strikes, dict):
            continue
        for strike, options in strikes.items():
            if not isinstance(options, list):
                continue
            for option in options:
                contract = _parse_contract(chain, option_type, actual_expiration, strike, option)
                if contract is not None:
                    yield contract


def find_contracts_by_premium(
    chain: dict,
    option_type: str,
    target_min: Decimal = Decimal("0.40"),
    target_max: Decimal = Decimal("0.50"),
    expiration_date: date | None = None,
) -> list[OptionContract]:
    """Find fallback contracts within the price band; no execution authority."""
    _map_name(option_type)
    if (
        not isinstance(target_min, Decimal)
        or not isinstance(target_max, Decimal)
        or not target_min.is_finite()
        or not target_max.is_finite()
        or target_min <= 0 or target_max < target_min
    ):
        raise ValueError("Invalid premium range")

    matches = [
        contract for contract in _iter_contracts(chain, option_type.strip().upper(), expiration_date)
        if target_min <= contract.ask <= target_max
    ]
    return sorted(
        matches,
        key=lambda contract: (
            abs(contract.ask - Decimal("0.45")),
            contract.ask - contract.bid,
        ),
    )


def find_contract_by_strike(
    chain: dict, option_type: str, strike_price: Decimal, expiration_date: date
) -> OptionContract | None:
    """Find an exact strike and expiration; never substitute another strike."""
    _map_name(option_type)
    if not isinstance(strike_price, Decimal) or not strike_price.is_finite():
        return None
    for contract in _iter_contracts(chain, option_type.strip().upper(), expiration_date):
        if contract.strike_price == strike_price:
            return contract
    return None


def find_contract_by_symbol(
    chain: dict, contract_symbol: str, expiration_date: date
) -> OptionContract | None:
    """Match the complete normalized Schwab contract symbol exactly."""
    if not isinstance(contract_symbol, str):
        return None
    requested = "".join(contract_symbol.upper().split())
    if not requested:
        return None
    for option_type in ("CALL", "PUT"):
        for contract in _iter_contracts(chain, option_type, expiration_date):
            if "".join(contract.symbol.upper().split()) == requested:
                return contract
    return None
