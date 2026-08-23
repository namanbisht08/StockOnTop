import pandas as pd

from app.core.config import get_strategy_config


class ScoringEngine:
    @staticmethod
    def score(row: pd.Series, setup: str) -> float:
        config = get_strategy_config().scoring
        total_score = 0.0

        # Trend
        if row["close"] > row["sma50"]:
            total_score += config.trend * 0.4
        if row["sma50"] > row["sma200"]:
            total_score += config.trend * 0.4
        if row.get("adx", 0) > 25:
            total_score += config.trend * 0.2

        # Breakout / Setup specific
        if setup == "BREAKOUT":
            total_score += config.breakout
        elif setup == "PULLBACK":
            total_score += (
                config.breakout * 0.8
            )  # slightly penalize pullback vs breakout in MVP

        # Volume
        rel_vol = row.get("relative_volume", 0)
        if rel_vol > 2.0:
            total_score += config.volume
        elif rel_vol > 1.2:
            total_score += config.volume * 0.5

        # Momentum
        rsi = row.get("rsi14", 0)
        if 55 <= rsi <= 65:
            total_score += config.momentum
        elif 50 <= rsi <= 70:
            total_score += config.momentum * 0.5

        # Relative Strength
        rs_20 = row.get("relative_strength_20d", 0)
        rs_60 = row.get("relative_strength_60d", 0)
        if rs_20 and rs_20 > 0:
            total_score += config.relative_strength * 0.5
        if rs_60 and rs_60 > 0:
            total_score += config.relative_strength * 0.5

        # Fundamentals - MVP skip or give flat score if data missing
        total_score += config.fundamentals * 0.5

        return min(total_score, 100.0)
