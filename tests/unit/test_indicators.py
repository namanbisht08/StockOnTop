import pandas as pd

from app.indicators.trend import add_sma


def test_sma():
    data = {"close": [1, 2, 3, 4, 5]}
    df = pd.DataFrame(data)
    df = add_sma(df, "close", 3)
    assert pd.isna(df["sma3"].iloc[0])
    assert pd.isna(df["sma3"].iloc[1])
    assert df["sma3"].iloc[2] == 2.0
    assert df["sma3"].iloc[3] == 3.0
    assert df["sma3"].iloc[4] == 4.0
