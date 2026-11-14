
import re

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from my_trading_simulator.market_data.contract_selector import (
    OptionContract,
)


OPTION_SYMBOL_PATTERN = re.compile(
    r"^([A-Z]+)\s+(\d{6})([CP])(\d{8})$"
)


def validate_contract_identity(
    contract: OptionContract,
    expected_underlying: str,
    expected_option_type: str,
    expected_expiration: date,
) -> tuple[bool, str]:
    """
    Validate that an option contract's OCC-style
    symbol agrees with its metadata and the
    requested trading instrument.

    Checks:
    - Underlying symbol
    - CALL/PUT type
    - Expiration date
    - Strike price

    Never modifies or substitutes the contract.
    """

    if contract is None:
        return False, "Missing option contract"

    if not isinstance(expected_underlying, str):
        return False, "Invalid expected underlying"

    if not isinstance(expected_option_type, str):
        return False, "Invalid expected option type"

    if (
        not isinstance(expected_expiration, date)
        or isinstance(expected_expiration, datetime)
    ):
        return False, "Invalid expected expiration"

    expected_underlying = expected_underlying.strip().upper()
    expected_option_type = expected_option_type.strip().upper()

    if expected_underlying not in {"SPY", "QQQ", "IWM"}:
        return False, "Unsupported expected underlying"

    if expected_option_type not in {"CALL", "PUT"}:
        return False, "Invalid expected option type"

    if not isinstance(contract.symbol, str):
        return False, "Invalid option symbol"

    match = OPTION_SYMBOL_PATTERN.fullmatch(
        contract.symbol.strip().upper()
    )

    if match is None:
        return False, "Invalid option symbol format"

    symbol_underlying, date_code, type_code, strike_code = (
        match.groups()
    )

    try:
        symbol_expiration = datetime.strptime(
            date_code,
            "%y%m%d",
        ).date()

        symbol_strike = (
            Decimal(strike_code) / Decimal("1000")
        )

        metadata_strike = Decimal(
            str(contract.strike_price)
        )

        if not metadata_strike.is_finite():
            return False, "Invalid contract strike"

    except (
        ValueError,
        TypeError,
        InvalidOperation,
    ):
        return False, "Invalid encoded contract details"

    symbol_option_type = (
        "CALL" if type_code == "C" else "PUT"
    )

    if symbol_underlying != expected_underlying:
        return False, "Option symbol underlying mismatch"

    if contract.underlying_symbol != expected_underlying:
        return False, "Contract underlying metadata mismatch"

    if symbol_option_type != expected_option_type:
        return False, "Option symbol type mismatch"

    if contract.option_type != expected_option_type:
        return False, "Contract option type metadata mismatch"

    if symbol_expiration != expected_expiration:
        return False, "Option symbol expiration mismatch"

    if contract.expiration_date != expected_expiration:
        return False, "Contract expiration metadata mismatch"

    if symbol_strike != metadata_strike:
        return False, "Option symbol strike mismatch"

    return True, "Contract identity is valid"
