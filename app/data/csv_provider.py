from datetime import date
from pathlib import Path

import pandas as pd

from app.data.base import MarketDataProvider, Quote

REQUIRED_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjusted_close",
]


class CSVProvider(MarketDataProvider):
    """Deterministic, reproducible data source for backtests and fixtures.

    Expects one CSV file per symbol at `{data_dir}/{symbol}.csv` with columns
    matching REQUIRED_COLUMNS (adjusted_close falls back to close if absent).
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    def _load(self, symbol: str) -> pd.DataFrame:
        path = self.data_dir / f"{symbol}.csv"
        if not path.exists():
            return pd.DataFrame()

        df = pd.read_csv(path)
        df.columns = [c.lower() for c in df.columns]
        if "adjusted_close" not in df.columns and "close" in df.columns:
            df["adjusted_close"] = df["close"]

        for col in REQUIRED_COLUMNS:
            if col not in df.columns:
                return pd.DataFrame()

        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.date
        return df[REQUIRED_COLUMNS].sort_values("timestamp").reset_index(drop=True)

    def get_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> pd.DataFrame:
        df = self._load(symbol)
        if df.empty:
            return df
        mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
        return df[mask].reset_index(drop=True)

    def get_quote(self, symbol: str) -> Quote:
        df = self._load(symbol)
        if df.empty:
            raise ValueError(f"No data available for {symbol}")
        last = df.iloc[-1]
        return Quote(
            symbol=symbol, price=float(last["close"]), timestamp=last["timestamp"]
        )

    def get_index_data(
        self, index: str, start: date, end: date, interval: str = "1d"
    ) -> pd.DataFrame:
        return self.get_ohlcv(index, start, end, interval)
