from datetime import date
from typing import Dict

import pandas as pd

from app.data.base import MarketDataProvider, Quote


class MockProvider(MarketDataProvider):
    """In-memory provider for unit tests - no network, no filesystem."""

    def __init__(self):
        self._ohlcv: Dict[str, pd.DataFrame] = {}
        self._quotes: Dict[str, Quote] = {}

    def set_ohlcv(self, symbol: str, df: pd.DataFrame) -> None:
        self._ohlcv[symbol] = df

    def set_quote(self, symbol: str, quote: Quote) -> None:
        self._quotes[symbol] = quote

    def get_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> pd.DataFrame:
        df = self._ohlcv.get(symbol, pd.DataFrame())
        if df.empty:
            return df
        mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
        return df[mask].reset_index(drop=True)

    def get_quote(self, symbol: str) -> Quote:
        if symbol not in self._quotes:
            raise ValueError(f"No mock quote configured for {symbol}")
        return self._quotes[symbol]

    def get_index_data(
        self, index: str, start: date, end: date, interval: str = "1d"
    ) -> pd.DataFrame:
        return self.get_ohlcv(index, start, end, interval)
