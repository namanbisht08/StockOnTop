import pandas as pd


def add_relative_volume(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df[f"volume_sma{period}"] = df["volume"].rolling(window=period).mean()
    # Replace 0 volume with NaN to avoid division by zero
    sma = df[f"volume_sma{period}"].replace(0, pd.NA)
    df["relative_volume"] = df["volume"] / sma
    return df
