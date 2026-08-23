from typing import Optional

import pandas as pd


class SetupDetector:
    @staticmethod
    def detect(row: pd.Series, regime: str) -> Optional[str]:
        # Only trade in BULLISH or NEUTRAL regime for now
        if regime == "BEARISH":
            return None

        is_breakout = SetupDetector._check_breakout(row)
        if is_breakout:
            return "BREAKOUT"

        is_pullback = SetupDetector._check_pullback(row)
        if is_pullback:
            return "PULLBACK"

        return None

    @staticmethod
    def _check_breakout(row: pd.Series) -> bool:
        close = row["close"]
        sma50 = row["sma50"]
        sma200 = row["sma200"]
        rel_vol = row.get("relative_volume", 0)
        rsi = row.get("rsi14", 0)

        if close > sma50 and sma50 > sma200 and rel_vol > 1.5 and 50 <= rsi <= 70:
            return True
        return False

    @staticmethod
    def _check_pullback(row: pd.Series) -> bool:
        close = row["close"]
        sma20 = row["sma20"]
        sma50 = row["sma50"]
        sma200 = row["sma200"]
        rel_vol = row.get("relative_volume", 1.0)

        if (
            close > sma200
            and sma50 > sma200
            and sma20 * 0.98 <= close <= sma20 * 1.02
            and rel_vol < 1.0
        ):
            return True
        return False
