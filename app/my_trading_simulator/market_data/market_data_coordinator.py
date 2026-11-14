
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from my_trading_simulator.config.settings import settings

from my_trading_simulator.market_data.contract_selector import (
    OptionContract,
    find_contracts_by_premium,
)

from my_trading_simulator.market_data.contract_identity import (
    validate_contract_identity,
)

from my_trading_simulator.market_data.schwab_client import (
    SchwabMarketDataClient,
)

from my_trading_simulator.market_data.validated_selector import (
    find_valid_contract_by_symbol,
    find_valid_explicit_contract,
)

from my_trading_simulator.market_data.premium_safety import (
    validate_contract_premium,
)

from my_trading_simulator.market_data.quote_validator import (
    validate_contract_for_paper_trade,
)

from my_trading_simulator.market_data.strike_safety import (
    validate_strike_with_stock_quote,
)


class MarketDataCoordinator:
    """
    Coordinates read-only Schwab market data retrieval
    and safe option contract selection.

    Responsibilities:
    - Retrieve 0DTE option chains.
    - Retrieve current underlying stock quotes.
    - Honor Casey's exact contract instructions.
    - Apply configurable premium safety limits.
    - Validate option quote freshness and spread.
    - Validate contract identity.
    - Validate underlying quote and strike distance.
    - Evaluate multiple fallback candidates safely.

    This class does NOT submit real brokerage orders
    or modify simulated account balances.
    """

    def __init__(
        self,
        market_data_client: SchwabMarketDataClient | None = None,
    ):
        self.client = (
            market_data_client
            if market_data_client is not None
            else SchwabMarketDataClient()
        )

    @staticmethod
    def _validate_selected_contract(
        contract: OptionContract | None,
        symbol: str,
        option_type: str,
        trading_date: date,
    ) -> OptionContract | None:
        """
        Validate that the selected contract's symbol
        and metadata match the requested instrument.

        Checks:
        - Underlying symbol
        - CALL or PUT type
        - Expiration date
        - Strike encoded in the option symbol

        Returns None if identity validation fails.
        """

        if contract is None:
            return None

        valid, _ = validate_contract_identity(
            contract=contract,
            expected_underlying=symbol,
            expected_option_type=option_type,
            expected_expiration=trading_date,
        )

        if not valid:
            return None

        return contract

    def select_contract(
        self,
        symbol: str,
        option_type: Literal["CALL", "PUT"],
        trading_date: date,
        strike_price: Decimal | None = None,
        contract_symbol: str | None = None,
        now: datetime | None = None,
    ) -> OptionContract | None:
        """
        Safely select one 0DTE option contract.

        Selection priority:

        1. Casey's exact full option symbol.
        2. Casey's exact strike price.
        3. Configured fallback contract selection.

        Explicit instructions never trigger automatic
        substitution to another contract.

        Fallback selection may evaluate multiple
        candidates until one passes all validations.

        Returns None if no safe contract is available.
        """

        # Step 1: Normalize and validate underlying.
        if not isinstance(symbol, str):
            return None

        symbol = symbol.strip().upper()

        if symbol not in {"SPY", "QQQ", "IWM"}:
            return None

        # Step 2: Validate option type.
        if option_type not in {"CALL", "PUT"}:
            return None

        # Step 3: Reject conflicting contract instructions.
        if (
            contract_symbol is not None
            and strike_price is not None
        ):
            return None

        # Step 4: Fetch the 0DTE option chain.
        try:
            chain = self.client.get_0dte_option_chain(
                symbol=symbol,
                trading_date=trading_date,
                strike_count=25,
            )
        except Exception:
            return None

        # Step 5: Casey provided an exact option symbol.
        if contract_symbol is not None:
            try:
                stock_quote = self.client.get_stock_quote(
                    symbol
                )
            except Exception:
                return None

            contract = find_valid_contract_by_symbol(
                chain=chain,
                contract_symbol=contract_symbol,
                trading_date=trading_date,
                now=now,
                stock_quote_response=stock_quote,
            )

            return self._validate_selected_contract(
                contract=contract,
                symbol=symbol,
                option_type=option_type,
                trading_date=trading_date,
            )

        # Step 6: Casey provided an exact strike.
        if strike_price is not None:
            try:
                stock_quote = self.client.get_stock_quote(
                    symbol
                )
            except Exception:
                return None

            contract = find_valid_explicit_contract(
                chain=chain,
                option_type=option_type,
                strike_price=strike_price,
                trading_date=trading_date,
                now=now,
                stock_quote_response=stock_quote,
            )

            return self._validate_selected_contract(
                contract=contract,
                symbol=symbol,
                option_type=option_type,
                trading_date=trading_date,
            )

        # Step 7: Fallback selection.
        #
        # Casey has not specified an exact contract.
        # We can evaluate multiple candidates safely.

        # Retrieve the underlying quote once.
        try:
            stock_quote = self.client.get_stock_quote(
                symbol
            )
        except Exception:
            return None

        # Discover fallback candidates within
        # the configured premium range.
        candidates = find_contracts_by_premium(
            chain=chain,
            option_type=option_type,
            target_min=settings.fallback_minimum_premium,
            target_max=settings.fallback_maximum_premium,
            expiration_date=trading_date,
        )

        # Step 8: Evaluate candidates individually.
        for contract in candidates:

            # Verify contract identity.
            validated_contract = (
                self._validate_selected_contract(
                    contract=contract,
                    symbol=symbol,
                    option_type=option_type,
                    trading_date=trading_date,
                )
            )

            if validated_contract is None:
                continue

            # Check fallback premium safety.
            premium_valid, _ = validate_contract_premium(
                ask=validated_contract.ask,
                is_explicit=False,
            )

            if not premium_valid:
                continue

            # Check option quote freshness and spread.
            quote_valid, _ = validate_contract_for_paper_trade(
                contract=validated_contract,
                trading_date=trading_date,
                now=now,
            )

            if not quote_valid:
                continue

            # Check underlying price and strike distance.
            strike_valid, _ = validate_strike_with_stock_quote(
                strike_price=validated_contract.strike_price,
                symbol=symbol,
                stock_quote_response=stock_quote,
                now=now,
            )

            if not strike_valid:
                continue

            # Candidate passed every safety check.
            return validated_contract

        # No candidate passed all safety checks.
        return None
