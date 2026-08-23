from datetime import date, timedelta

import pandas as pd
import pytest

from app.backtest.engine import run_backtest
from app.indicators.engine import calculate_indicators
from app.strategy.market_regime import MarketRegime
from app.strategy.strategy import StrategyEngine

BREAKOUT_INDEX = 259  # last index of the pre-breakout history
N_PRE = 260  # trading days up to and including the breakout day
N_POST = 6  # resolution days after the breakout, engineered to hit target_1


def _trading_dates(start: date, n: int) -> list:
    dates = []
    d = start
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    return dates


def _build_stock_history() -> pd.DataFrame:
    """A hand-tuned OHLCV series: a long oscillating uptrend (mixed up/down
    days so RSI isn't pinned at 100), a flat consolidation just under
    resistance, a breakout day with a volume spike, then a clean rally that
    fills the entry zone and hits target_1. Every number here was verified
    against the real indicator/strategy code (see build_fixture.py in the
    dev scratchpad) rather than hand-derived, since RSI/ADX depend on
    rolling-window arithmetic that isn't practical to compute by hand.
    """
    dates = _trading_dates(date(2023, 1, 2), N_PRE + N_POST)
    rows = []
    price = 150.0
    volume = 500_000

    for i, d in enumerate(dates):
        if i < 230:
            delta = -0.75 if i % 3 == 2 else 0.5
            open_ = price
            price += delta
            close = price
            high, low = max(open_, close) + 0.3, min(open_, close) - 0.3
            vol = volume
        elif i < BREAKOUT_INDEX:
            delta = -0.2 if i % 2 else 0.15
            open_ = price
            price += delta
            close = price
            high, low = max(open_, close) + 0.3, min(open_, close) - 0.3
            vol = volume
        elif i == BREAKOUT_INDEX:
            open_ = price + 0.3
            close = price + 1.6
            high, low = close + 0.5, open_ - 0.2
            price = close
            vol = int(volume * 2.6)
        else:
            # Post-breakout rally: day 1 fills the entry zone, day 5 pushes
            # through target_1 (177.892 given the breakout day's levels).
            step = i - BREAKOUT_INDEX
            open_ = price + 0.5
            close = price + (1.5 if step < 5 else 1.5)
            high = close + 0.3
            low = open_ - 0.2
            price = close
            vol = volume

        rows.append(
            {
                "timestamp": d,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": vol,
                "adjusted_close": close,
            }
        )
    return pd.DataFrame(rows)


def _build_index_history() -> pd.DataFrame:
    dates = _trading_dates(date(2023, 1, 2), N_PRE + N_POST)
    rows = []
    price = 20_000.0
    for d in dates:
        price += 1.5
        rows.append(
            {
                "timestamp": d,
                "open": price,
                "high": price + 5,
                "low": price - 5,
                "close": price,
                "volume": 0,
                "adjusted_close": price,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def fixture_data():
    stock_df = _build_stock_history()
    index_df = _build_index_history()
    breakout_date = stock_df.iloc[BREAKOUT_INDEX]["timestamp"]
    return stock_df, index_df, breakout_date


def test_fixture_produces_expected_breakout_plan(fixture_data):
    """Locks in the deterministic strategy pipeline's output on this fixture.
    A silent change to filters/setup detection/scoring/risk levels should
    break this test rather than only being noticed in a live scan.
    """
    stock_df, index_df, breakout_date = fixture_data

    history_slice = stock_df[stock_df["timestamp"] <= breakout_date]
    index_slice = calculate_indicators(index_df[index_df["timestamp"] <= breakout_date])
    indicators = calculate_indicators(history_slice, index_slice)
    latest = indicators.iloc[-1]
    regime = MarketRegime.determine(index_slice.iloc[-1]).value

    plan = StrategyEngine.evaluate_candidate(latest, regime, symbol="FIXTURE")

    assert plan is not None
    assert plan.setup_type == "BREAKOUT"
    assert plan.score == pytest.approx(82.5)
    assert plan.entry_low == pytest.approx(171.05)
    assert plan.entry_high == pytest.approx(172.7605)
    assert plan.stop_loss == pytest.approx(167.629)
    assert plan.target_1 == pytest.approx(177.892)
    assert plan.risk_reward == pytest.approx(2.0)
    assert plan.quantity == 116


def test_backtest_engine_regression_fixture(fixture_data):
    stock_df, index_df, breakout_date = fixture_data
    start_date = breakout_date - timedelta(days=6)
    end_date = breakout_date

    trades = run_backtest({"FIXTURE": stock_df}, index_df, start_date, end_date)

    assert len(trades) == 1
    trade = trades[0]

    assert trade.symbol == "FIXTURE"
    assert trade.setup_type == "BREAKOUT"
    assert trade.signal_date == breakout_date
    assert trade.exit_reason == "TARGET_1_HIT"
    assert trade.quantity == 116
    assert trade.holding_days == 5
    assert trade.entry_date == breakout_date + timedelta(days=3)  # next trading day
    assert trade.exit_date == breakout_date + timedelta(days=7)
    # Day after breakout opens at 171.55, inside the [171.05, 172.76] zone.
    assert trade.entry_price == pytest.approx(171.55 * 1.0005, rel=1e-6)
    assert trade.net_pnl > 0
