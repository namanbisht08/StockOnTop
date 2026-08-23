from dataclasses import dataclass
from datetime import date
from typing import List, Tuple, cast

import numpy as np
import pandas as pd

from app.backtest.simulator import TradeResult

TRADING_DAYS_PER_YEAR = 252


@dataclass
class BacktestMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    gross_profit: float
    gross_loss: float
    net_pnl: float
    expectancy: float
    avg_holding_days: float
    median_holding_days: float
    best_trade: float
    worst_trade: float
    longest_winning_streak: int
    longest_losing_streak: int
    cagr: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float


def _empty_metrics() -> BacktestMetrics:
    return BacktestMetrics(
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate=0.0,
        avg_win=0.0,
        avg_loss=0.0,
        profit_factor=0.0,
        gross_profit=0.0,
        gross_loss=0.0,
        net_pnl=0.0,
        expectancy=0.0,
        avg_holding_days=0.0,
        median_holding_days=0.0,
        best_trade=0.0,
        worst_trade=0.0,
        longest_winning_streak=0,
        longest_losing_streak=0,
        cagr=0.0,
        max_drawdown=0.0,
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        calmar_ratio=0.0,
    )


def _streaks(win_flags: List[bool]) -> Tuple[int, int]:
    best_win = best_loss = cur_win = cur_loss = 0
    for is_win in win_flags:
        if is_win:
            cur_win += 1
            cur_loss = 0
        else:
            cur_loss += 1
            cur_win = 0
        best_win = max(best_win, cur_win)
        best_loss = max(best_loss, cur_loss)
    return best_win, best_loss


def build_equity_curve(trades: List[TradeResult], initial_capital: float) -> pd.Series:
    """Realized-P&L equity curve indexed by exit date.

    This tracks capital as if each trade's net P&L lands on its exit date -
    it is not a daily mark-to-market curve, so it doesn't reflect unrealized
    swings while positions are open. That's an acceptable simplification for
    a swing strategy holding a handful of short-lived positions, but it will
    understate true intra-period volatility.
    """
    closed = sorted(
        (t for t in trades if t.exit_date is not None),
        key=lambda t: cast(date, t.exit_date),
    )
    if not closed:
        return pd.Series(dtype=float)

    dates = pd.to_datetime([t.exit_date for t in closed])
    equity = initial_capital + np.cumsum([t.net_pnl for t in closed])
    return pd.Series(equity, index=dates)


def calculate_metrics(
    trades: List[TradeResult], initial_capital: float
) -> BacktestMetrics:
    filled = [t for t in trades if t.exit_date is not None]
    if not filled:
        return _empty_metrics()

    pnls = [t.net_pnl for t in filled]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total_trades = len(filled)
    winning_trades = len(wins)
    losing_trades = len(losses)
    win_rate = winning_trades / total_trades * 100

    gross_profit = float(sum(wins))
    gross_loss = float(abs(sum(losses)))
    avg_win = gross_profit / winning_trades if winning_trades else 0.0
    avg_loss = gross_loss / losing_trades if losing_trades else 0.0
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = float("inf") if gross_profit > 0 else 0.0

    net_pnl = float(sum(pnls))
    expectancy = net_pnl / total_trades

    holding_days = [t.holding_days for t in filled]
    avg_holding_days = float(np.mean(holding_days))
    median_holding_days = float(np.median(holding_days))

    best_trade = float(max(pnls))
    worst_trade = float(min(pnls))

    longest_winning_streak, longest_losing_streak = _streaks([p > 0 for p in pnls])

    equity = build_equity_curve(filled, initial_capital)

    cagr = max_drawdown = sharpe_ratio = sortino_ratio = calmar_ratio = 0.0
    if len(equity) >= 2:
        years = (equity.index[-1] - equity.index[0]).days / 365.25
        if years > 0 and equity.iloc[0] > 0:
            cagr = ((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) * 100

        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_drawdown = float(drawdown.min() * 100)

        period_returns = equity.pct_change().dropna()
        if len(period_returns) > 1 and period_returns.std() > 0:
            sharpe_ratio = float(
                period_returns.mean()
                / period_returns.std()
                * np.sqrt(TRADING_DAYS_PER_YEAR)
            )

        downside = period_returns[period_returns < 0]
        if len(downside) > 1 and downside.std() > 0:
            sortino_ratio = float(
                period_returns.mean() / downside.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
            )

        if max_drawdown != 0:
            calmar_ratio = cagr / abs(max_drawdown)

    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=net_pnl,
        expectancy=expectancy,
        avg_holding_days=avg_holding_days,
        median_holding_days=median_holding_days,
        best_trade=best_trade,
        worst_trade=worst_trade,
        longest_winning_streak=longest_winning_streak,
        longest_losing_streak=longest_losing_streak,
        cagr=cagr,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
    )


def monthly_returns(trades: List[TradeResult], initial_capital: float) -> pd.Series:
    equity = build_equity_curve(trades, initial_capital)
    if equity.empty:
        return pd.Series(dtype=float)
    monthly = equity.resample("ME").last().ffill()
    return monthly.pct_change().dropna() * 100


def yearly_returns(trades: List[TradeResult], initial_capital: float) -> pd.Series:
    equity = build_equity_curve(trades, initial_capital)
    if equity.empty:
        return pd.Series(dtype=float)
    yearly = equity.resample("YE").last().ffill()
    return yearly.pct_change().dropna() * 100
