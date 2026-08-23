from datetime import date

import pandas as pd
import yfinance as yf

from app.data.base import MarketDataProvider, Quote


class YahooFinanceProvider(MarketDataProvider):
    def _format_symbol(self, symbol: str) -> str:
        if not symbol.endswith(".NS") and not symbol.startswith("^"):
            return f"{symbol}.NS"
        return symbol

    def get_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> pd.DataFrame:
        formatted_symbol = self._format_symbol(symbol)
        data = yf.download(
            formatted_symbol,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=False,
            progress=False,
        )
        if data.empty:
            return pd.DataFrame()

        # If MultiIndex columns (yf.download behavior for single symbol sometimes), flatten
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        df = data.reset_index()
        df.columns = [c.lower() for c in df.columns]

        # Rename date/datetime to timestamp
        if "date" in df.columns:
            df.rename(columns={"date": "timestamp"}, inplace=True)
        elif "datetime" in df.columns:
            df.rename(columns={"datetime": "timestamp"}, inplace=True)

        # Ensure timestamp is just date if interval is 1d
        if interval == "1d":
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.date

        # Check required columns
        required = ["timestamp", "open", "high", "low", "close", "volume", "adj close"]
        for col in required:
            if col not in df.columns:
                if col == "adj close" and "close" in df.columns:
                    df["adj close"] = df["close"]
                else:
                    return pd.DataFrame()

        df.rename(columns={"adj close": "adjusted_close"}, inplace=True)

        return df[
            ["timestamp", "open", "high", "low", "close", "volume", "adjusted_close"]
        ]

    def get_quote(self, symbol: str) -> Quote:
        formatted_symbol = self._format_symbol(symbol)
        ticker = yf.Ticker(formatted_symbol)
        history = ticker.history(period="1d")
        if history.empty:
            raise ValueError(f"No quote available for {symbol}")

        price = float(history["Close"].iloc[-1])
        timestamp = pd.to_datetime(history.index[-1]).date()
        return Quote(symbol=symbol, price=price, timestamp=timestamp)

    def get_index_data(
        self, index: str, start: date, end: date, interval: str = "1d"
    ) -> pd.DataFrame:
        return self.get_ohlcv(index, start, end, interval)
