import pandas as pd

from app.core.config import get_strategy_config


class HardFilters:
    @staticmethod
    def is_eligible(row: pd.Series) -> bool:
        config = get_strategy_config().screening

        # Check basic price constraint
        if row["close"] < config.min_price:
            return False

        # Check basic liquidity (price * volume)
        if pd.notna(row.get("volume_sma20")):
            turnover = row["close"] * row["volume_sma20"]
            if turnover < config.min_average_daily_turnover:
                return False

        # Required indicators must not be NaN
        required_cols = ["sma50", "sma200", "rsi14", "atr14"]
        for col in required_cols:
            if col not in row or pd.isna(row[col]):
                return False

        return True
