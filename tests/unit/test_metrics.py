from datetime import date

import pytest

from app.backtest.metrics import build_equity_curve, calculate_metrics
from app.backtest.simulator import TradeResult


def _trade(net_pnl: float, exit_date: date, holding_days: int = 5) -> TradeResult:
    return TradeResult(
        symbol="X",
        setup_type="BREAKOUT",
        score=80.0,
        signal_date=exit_date,
        entry_date=exit_date,
        entry_price=100.0,
        exit_date=exit_date,
        exit_price=100.0 + net_pnl / 10,
        exit_reason="TARGET_1_HIT" if net_pnl > 0 else "STOPPED_OUT",
        quantity=10,
        gross_pnl=net_pnl,
        charges=0.0,
        net_pnl=net_pnl,
        return_pct=net_pnl / 1000 * 100,
        holding_days=holding_days,
    )


def test_calculate_metrics_on_empty_trades_returns_zeros():
    metrics = calculate_metrics([], initial_capital=100_000.0)
    assert metrics.total_trades == 0
    assert metrics.win_rate == 0.0
    assert metrics.profit_factor == 0.0


def test_calculate_metrics_basic_counts_and_ratios():
    trades = [
        _trade(1000.0, date(2023, 1, 10)),
        _trade(-400.0, date(2023, 2, 10)),
        _trade(600.0, date(2023, 3, 10)),
        _trade(-200.0, date(2023, 4, 10)),
    ]

    metrics = calculate_metrics(trades, initial_capital=100_000.0)

    assert metrics.total_trades == 4
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 2
    assert metrics.win_rate == pytest.approx(50.0)
    assert metrics.gross_profit == pytest.approx(1600.0)
    assert metrics.gross_loss == pytest.approx(600.0)
    assert metrics.profit_factor == pytest.approx(1600.0 / 600.0)
    assert metrics.net_pnl == pytest.approx(1000.0)
    assert metrics.expectancy == pytest.approx(250.0)
    assert metrics.avg_win == pytest.approx(800.0)
    assert metrics.avg_loss == pytest.approx(300.0)
    assert metrics.best_trade == pytest.approx(1000.0)
    assert metrics.worst_trade == pytest.approx(-400.0)
    assert metrics.avg_holding_days == pytest.approx(5.0)
    assert metrics.median_holding_days == pytest.approx(5.0)


def test_calculate_metrics_streaks():
    trades = [
        _trade(100.0, date(2023, 1, 1)),
        _trade(100.0, date(2023, 1, 8)),
        _trade(-50.0, date(2023, 1, 15)),
        _trade(100.0, date(2023, 1, 22)),
        _trade(-50.0, date(2023, 1, 29)),
        _trade(-50.0, date(2023, 2, 5)),
        _trade(-50.0, date(2023, 2, 12)),
    ]
    metrics = calculate_metrics(trades, initial_capital=100_000.0)
    assert metrics.longest_winning_streak == 2
    assert metrics.longest_losing_streak == 3


def test_calculate_metrics_profit_factor_is_infinite_with_no_losses():
    trades = [_trade(500.0, date(2023, 1, 1)), _trade(300.0, date(2023, 2, 1))]
    metrics = calculate_metrics(trades, initial_capital=100_000.0)
    assert metrics.profit_factor == float("inf")


def test_build_equity_curve_orders_by_exit_date_and_accumulates():
    trades = [
        _trade(500.0, date(2023, 3, 1)),
        _trade(-200.0, date(2023, 1, 1)),  # earlier exit date, listed second
    ]
    equity = build_equity_curve(trades, initial_capital=10_000.0)

    assert list(equity.values) == [9_800.0, 10_300.0]  # sorted by exit date


def test_calculate_metrics_cagr_and_drawdown_match_equity_curve_formula():
    trades = [
        _trade(10_000.0, date(2020, 1, 1)),
        _trade(-30_000.0, date(2020, 7, 1)),
        _trade(20_000.0, date(2021, 1, 1)),
    ]
    initial_capital = 100_000.0
    metrics = calculate_metrics(trades, initial_capital)
    equity = build_equity_curve(trades, initial_capital)

    years = (equity.index[-1] - equity.index[0]).days / 365.25
    expected_cagr = ((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) * 100
    running_max = equity.cummax()
    expected_max_dd = float(((equity - running_max) / running_max).min() * 100)

    assert metrics.cagr == pytest.approx(expected_cagr)
    assert metrics.max_drawdown == pytest.approx(expected_max_dd)
    assert metrics.max_drawdown < 0
