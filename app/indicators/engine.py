import pandas as pd

from app.indicators.momentum import add_macd, add_roc, add_rsi
from app.indicators.relative_strength import add_relative_strength
from app.indicators.trend import add_adx, add_ema, add_sma
from app.indicators.volatility import add_atr
from app.indicators.volume import add_relative_volume


def calculate_indicators(
    df: pd.DataFrame, df_index: pd.DataFrame = None
) -> pd.DataFrame:
    if df.empty:
        return df

    # Make a copy to avoid SettingWithCopyWarning
    df = df.copy()

    # Sort by timestamp
    df = df.sort_values(by="timestamp").reset_index(drop=True)

    # Trend
    df = add_sma(df, "close", 20)
    df = add_sma(df, "close", 50)
    df = add_sma(df, "close", 200)
    df = add_ema(df, "close", 20)
    df = add_ema(df, "close", 50)
    df = add_adx(df, 14)

    # Momentum
    df = add_rsi(df, "close", 14)
    df = add_macd(df, "close")
    df = add_roc(df, "close", 20)
    df = add_roc(df, "close", 60)

    # Volatility
    df = add_atr(df, 14)

    # Volume
    df = add_relative_volume(df, 20)

    # Relative Strength
    if df_index is not None and not df_index.empty:
        df_index = df_index.sort_values(by="timestamp").reset_index(drop=True)
        df = add_relative_strength(df, df_index, periods=[20, 60])
    else:
        df["relative_strength_20d"] = None
        df["relative_strength_60d"] = None

    return df
