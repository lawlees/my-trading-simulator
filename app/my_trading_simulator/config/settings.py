from decimal import Decimal
from typing import Literal

from pydantic import Field
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
    starting_balance: Decimal = Field(default=Decimal("7000"), gt=0)

    # Risk management
    max_position_allocation: Decimal = Field(default=Decimal("400"), gt=0)
    max_loss_per_trade: Decimal = Field(default=Decimal("150"), gt=0)

    # Standard equity/ETF option contract multiplier
    option_contract_multiplier: int = Field(default=100, gt=0)

    # Trading configuration
    options_expiration: Literal["0DTE"] = "0DTE"
    supported_symbols: tuple[str, ...] = ("SPY", "QQQ", "IWM")

    # Strategy configuration
    ema_period: int = Field(default=13, ge=1)
    candle_interval_minutes: int = Field(default=2, ge=1)

    # Profit taking
    profit_take_fraction: Decimal = Field(
        default=Decimal("0.75"),
        gt=0,
        lt=1,
    )


    # Additional entry sizing
    add_position_fraction: Decimal = Decimal("0.50")
    max_additions_per_trade: int = 1

    # Light trades use half the normal allocation and risk.
    light_position_fraction: Decimal = Decimal("0.50")


settings = Settings()