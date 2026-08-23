import pandas as pd


def add_relative_strength(
    df_stock: pd.DataFrame, df_index: pd.DataFrame, periods: list[int] = None
) -> pd.DataFrame:
    periods = periods or [20, 60]
    # Ensure aligned timestamps
    df = df_stock.copy()

    # We will use close prices and pct_change
    index_returns = df_index.set_index("timestamp")["close"]
    stock_returns = df.set_index("timestamp")["close"]

    for period in periods:
        stock_ret = stock_returns.pct_change(periods=period)
        idx_ret = index_returns.pct_change(periods=period)

        # Align index
        rs = stock_ret - idx_ret

        # Map back to dataframe
        df[f"relative_strength_{period}d"] = df["timestamp"].map(rs)

    return df
