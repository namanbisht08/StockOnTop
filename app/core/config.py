from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class PortfolioConfig(BaseModel):
    capital: float = 100000.0
    max_positions: int = 4
    max_portfolio_exposure_pct: float = 80.0
    reserve_cash_pct: float = 20.0


class RiskConfig(BaseModel):
    max_risk_per_trade_pct: float = 1.0
    max_risk_per_trade_absolute: float = 1000.0
    min_risk_reward: float = 2.0
    max_stop_loss_pct: float = 8.0
    min_stop_loss_pct: float = 2.0


class ScreeningConfig(BaseModel):
    min_price: float = 100.0
    min_average_daily_turnover: float = 50000000.0
    min_average_volume_period: int = 20


class TechnicalConfig(BaseModel):
    sma_fast: int = 20
    sma_medium: int = 50
    sma_slow: int = 200
    rsi_period: int = 14
    atr_period: int = 14
    volume_period: int = 20


class ScoringConfig(BaseModel):
    trend: int = 25
    breakout: int = 20
    volume: int = 15
    momentum: int = 15
    relative_strength: int = 15
    fundamentals: int = 10


class SelectionConfig(BaseModel):
    minimum_score: int = 75
    candidates: int = 10
    final_picks: int = 3


class CostsConfig(BaseModel):
    """Illustrative placeholders, not verified current rates.

    Verify against actual SEBI/exchange/broker schedules before using this
    for anything beyond research-grade backtesting.
    """

    brokerage_pct: float = 0.03
    brokerage_max: float = 20.0
    stt_sell_pct: float = 0.025
    exchange_txn_pct: float = 0.00297
    gst_pct: float = 18.0
    sebi_charges_pct: float = 0.0001
    stamp_duty_buy_pct: float = 0.015
    slippage_pct: float = 0.05


class BacktestConfig(BaseModel):
    entry_expiry_days: int = 5
    max_holding_days: int = 20
    extended_entry_pct: float = 3.0


class StrategyConfig(BaseModel):
    portfolio: PortfolioConfig = PortfolioConfig()
    risk: RiskConfig = RiskConfig()
    screening: ScreeningConfig = ScreeningConfig()
    technical: TechnicalConfig = TechnicalConfig()
    scoring: ScoringConfig = ScoringConfig()
    selection: SelectionConfig = SelectionConfig()
    costs: CostsConfig = CostsConfig()
    backtest: BacktestConfig = BacktestConfig()


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/swing_trader.db"
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    log_level: str = "DEBUG"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


@lru_cache()
def get_strategy_config() -> StrategyConfig:
    config_path = Path("config/strategy.yaml")
    if not config_path.exists():
        return StrategyConfig()

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f) or {}

    return StrategyConfig(**config_data)
