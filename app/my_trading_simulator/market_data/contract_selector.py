
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


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


def find_contracts_by_premium(
    chain: dict,
    option_type: str,
    target_min: Decimal = Decimal("0.40"),
    target_max: Decimal = Decimal("0.50"),
    expiration_date: date | None = None,
) -> list[OptionContract]:
    """
    Find option contracts within a target ask range.

    If expiration_date is provided, only contracts
    expiring on that exact date are returned.

    This function does not authorize trades.
    Quote freshness and liquidity must be
    validated separately.
    """

    option_type = option_type.strip().upper()

    if option_type not in {"CALL", "PUT"}:
        raise ValueError(
            "option_type must be CALL or PUT"
        )

    if target_min <= 0 or target_max < target_min:
        raise ValueError("Invalid premium range")

    map_name = (
        "callExpDateMap"
        if option_type == "CALL"
        else "putExpDateMap"
    )

    matches = []

    for expiration_key, strikes in chain.get(
        map_name, {}
    ).items():

        contract_expiration = date.fromisoformat(
            expiration_key.split(":")[0]
        )

        # Only select contracts for the requested date
        if (
            expiration_date is not None
            and contract_expiration != expiration_date
        ):
            continue

        for strike, contracts in strikes.items():
            for option in contracts:

                bid_value = option.get("bid")
                ask_value = option.get("ask")

                if bid_value is None or ask_value is None:
                    continue

                bid = Decimal(str(bid_value))
                ask = Decimal(str(ask_value))

                # Reject invalid bid/ask quotes
                if bid < 0 or ask <= 0 or bid > ask:
                    continue

                # Apply preferred premium range
                if not target_min <= ask <= target_max:
                    continue

                matches.append(
                    OptionContract(
                        symbol=option["symbol"],
                        underlying_symbol=chain["symbol"],
                        option_type=option_type,
                        expiration_date=contract_expiration,
                        strike_price=Decimal(str(strike)),
                        bid=bid,
                        ask=ask,
                        volume=int(
                            option.get("totalVolume") or 0
                        ),
                        quote_timestamp_ms=option.get("quoteTimeInLong"),
                    )
                )

    # Prefer contracts closest to $0.45,
    # then those with tighter bid/ask spreads.
    return sorted(
        matches,
        key=lambda contract: (
            abs(
                contract.ask - Decimal("0.45")
            ),
            contract.ask - contract.bid,
        ),
    )


def find_contract_by_strike(
    chain: dict,
    option_type: str,
    strike_price: Decimal,
    expiration_date: date,
) -> OptionContract | None:
    """
    Find the exact contract requested by Casey.

    Does not apply the preferred premium range.
    Returns None if the contract is unavailable.

    Quote freshness and liquidity must be
    validated separately.
    """

    option_type = option_type.strip().upper()

    if option_type not in {"CALL", "PUT"}:
        raise ValueError(
            "option_type must be CALL or PUT"
        )

    map_name = (
        "callExpDateMap"
        if option_type == "CALL"
        else "putExpDateMap"
    )

    for expiration_key, strikes in chain.get(
        map_name, {}
    ).items():

        actual_expiration = date.fromisoformat(
            expiration_key.split(":")[0]
        )

        if actual_expiration != expiration_date:
            continue

        for strike, contracts in strikes.items():

            if Decimal(str(strike)) != strike_price:
                continue

            for option in contracts:

                bid_value = option.get("bid")
                ask_value = option.get("ask")

                if bid_value is None or ask_value is None:
                    continue

                bid = Decimal(str(bid_value))
                ask = Decimal(str(ask_value))

                # Reject invalid bid/ask quotes
                if bid < 0 or ask <= 0 or bid > ask:
                    continue

                return OptionContract(
                    symbol=option["symbol"],
                    underlying_symbol=chain["symbol"],
                    option_type=option_type,
                    expiration_date=actual_expiration,
                    strike_price=Decimal(str(strike)),
                    bid=bid,
                    ask=ask,
                    volume=int(
                        option.get("totalVolume") or 0
                    ),
                    quote_timestamp_ms=option.get("quoteTimeInLong"),
                )

    return None


def find_contract_by_symbol(
    chain: dict,
    contract_symbol: str,
    expiration_date: date,
) -> OptionContract | None:
    """
    Find the exact option contract by its full symbol.

    Handles differences in whitespace, including
    Schwab's padded option symbols.

    Does not substitute a different contract.
    Does not apply the preferred premium range.

    Quote freshness and liquidity must be
    validated separately.
    """

    # Normalize whitespace without changing
    # the contract's actual identity.
    requested_symbol = "".join(
        contract_symbol.upper().split()
    )

    if not requested_symbol:
        return None

    for option_type, map_name in (
        ("CALL", "callExpDateMap"),
        ("PUT", "putExpDateMap"),
    ):
        for expiration_key, strikes in chain.get(
            map_name, {}
        ).items():

            actual_expiration = date.fromisoformat(
                expiration_key.split(":")[0]
            )

            if actual_expiration != expiration_date:
                continue

            for strike, contracts in strikes.items():
                for option in contracts:

                    actual_symbol = "".join(
                        str(option.get("symbol", ""))
                        .upper()
                        .split()
                    )

                    if actual_symbol != requested_symbol:
                        continue

                    bid_value = option.get("bid")
                    ask_value = option.get("ask")

                    if bid_value is None or ask_value is None:
                        return None

                    bid = Decimal(str(bid_value))
                    ask = Decimal(str(ask_value))

                    if bid < 0 or ask <= 0 or bid > ask:
                        return None

                    return OptionContract(
                        symbol=option["symbol"],
                        underlying_symbol=chain["symbol"],
                        option_type=option_type,
                        expiration_date=actual_expiration,
                        strike_price=Decimal(str(strike)),
                        bid=bid,
                        ask=ask,
                        volume=int(
                            option.get("totalVolume") or 0
                        ),
                        quote_timestamp_ms=option.get(
                            "quoteTimeInLong"
                        ),
                    )

    return None
