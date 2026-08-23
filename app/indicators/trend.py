import numpy as np
import pandas as pd


def add_sma(df: pd.DataFrame, column: str, period: int) -> pd.DataFrame:
    df[f"sma{period}"] = df[column].rolling(window=period).mean()
    return df


def add_ema(df: pd.DataFrame, column: str, period: int) -> pd.DataFrame:
    df[f"ema{period}"] = df[column].ewm(span=period, adjust=False).mean()
    return df


def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = low.diff()

    # Handle NaN and boolean logic safely
    plus_dm = np.where((plus_dm > 0) & (plus_dm > -minus_dm), plus_dm, 0.0)
    minus_dm = np.where((minus_dm < 0) & (-minus_dm > plus_dm), -minus_dm, 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100 * (
        pd.Series(plus_dm).ewm(alpha=1 / period, adjust=False).mean() / atr
    )
    minus_di = 100 * (
        pd.Series(minus_dm).ewm(alpha=1 / period, adjust=False).mean() / atr
    )

    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()

    df["adx"] = adx
    return df
