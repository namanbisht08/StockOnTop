import pandas as pd


def add_rsi(df: pd.DataFrame, column: str = "close", period: int = 14) -> pd.DataFrame:
    delta = df[column].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    df[f"rsi{period}"] = 100 - (100 / (1 + rs))
    return df


def add_macd(
    df: pd.DataFrame,
    column: str = "close",
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    ema_fast = df[column].ewm(span=fast, adjust=False).mean()
    ema_slow = df[column].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()

    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_hist"] = macd_line - signal_line
    return df


def add_roc(df: pd.DataFrame, column: str = "close", period: int = 20) -> pd.DataFrame:
    df[f"return_{period}d"] = df[column].pct_change(periods=period)
    return df
