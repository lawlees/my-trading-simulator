
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "My Trading Simulator"
    trading_mode: Literal["PAPER"] = "PAPER"

    # Paper trading account
    starting_balance: Decimal = Field(
        default=Decimal("7000"),
        gt=0,
    )

    # Risk management
    max_position_allocation: Decimal = Field(
        default=Decimal("400"),
        gt=0,
    )
    max_loss_per_trade: Decimal = Field(
        default=Decimal("150"),
        gt=0,
    )

    # Standard equity/ETF option contract multiplier
    option_contract_multiplier: int = Field(
        default=100,
        gt=0,
    )

    # Trading configuration
    options_expiration: Literal["0DTE"] = "0DTE"
    supported_symbols: tuple[str, ...] = (
        "SPY",
        "QQQ",
        "IWM",
    )

    # Strategy configuration
    ema_period: int = Field(default=13, ge=1)
    candle_interval_minutes: int = Field(
        default=2,
        ge=1,
    )

    # Profit taking
    profit_take_fraction: Decimal = Field(
        default=Decimal("0.75"),
        gt=0,
        lt=1,
    )

    # Additional entry sizing
    add_position_fraction: Decimal = Field(
        default=Decimal("0.50"),
        gt=0,
        le=1,
    )
    max_additions_per_trade: int = Field(
        default=1,
        ge=0,
    )

    # Light trades use half the normal
    # allocation and risk.
    light_position_fraction: Decimal = Field(
        default=Decimal("0.50"),
        gt=0,
        le=1,
    )

    # Option premium safety limits
    # Explicit Casey contracts:
    # $0.20 <= ask < $2.00
    minimum_option_premium: Decimal = Field(
        default=Decimal("0.20"),
        gt=0,
    )
    maximum_option_premium: Decimal = Field(
        default=Decimal("2.00"),
        gt=0,
    )

    # Fallback selection:
    # $0.40 <= ask <= $0.50
    fallback_minimum_premium: Decimal = Field(
        default=Decimal("0.40"),
        gt=0,
    )
    fallback_maximum_premium: Decimal = Field(
        default=Decimal("0.50"),
        gt=0,
    )

    # Strike typo protection
    # Maximum distance from underlying price,
    # expressed as a percentage.
    max_strike_distance_percent: Decimal = Field(
        default=Decimal("2.00"),
        gt=0,
        le=100,
    )

    @model_validator(mode="after")
    def validate_trading_limits(self):
        if (
            self.maximum_option_premium
            <= self.minimum_option_premium
        ):
            raise ValueError(
                "Maximum option premium must exceed minimum"
            )

        if (
            self.fallback_maximum_premium
            < self.fallback_minimum_premium
        ):
            raise ValueError(
                "Invalid fallback premium range"
            )

        if (
            self.fallback_minimum_premium
            < self.minimum_option_premium
            or self.fallback_maximum_premium
            >= self.maximum_option_premium
        ):
            raise ValueError(
                "Fallback premiums must be within "
                "universal safety limits"
            )

        return self


settings = Settings()
