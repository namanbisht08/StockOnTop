import pandas as pd


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing
    df[f"atr{period}"] = tr.ewm(alpha=1 / period, adjust=False).mean()
    df[f"atr{period}_pct"] = (df[f"atr{period}"] / df["close"]) * 100

    return df
