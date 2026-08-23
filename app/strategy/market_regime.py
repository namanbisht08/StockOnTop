from enum import Enum

import pandas as pd


class MarketRegimeType(str, Enum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"


class MarketRegime:
    @staticmethod
    def determine(index_row: pd.Series) -> MarketRegimeType:
        if pd.isna(index_row.get("sma50")) or pd.isna(index_row.get("sma200")):
            return MarketRegimeType.NEUTRAL

        close = index_row["close"]
        sma50 = index_row["sma50"]
        sma200 = index_row["sma200"]

        # Simple deterministic rules
        if close > sma50 and sma50 > sma200:
            return MarketRegimeType.BULLISH
        elif close < sma50 and sma50 < sma200:
            return MarketRegimeType.BEARISH
        else:
            return MarketRegimeType.NEUTRAL
