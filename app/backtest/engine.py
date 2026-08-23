from datetime import date
from typing import Dict, List, Tuple

import pandas as pd

from app.backtest.simulator import TradeResult, simulate_trade
from app.core.config import get_strategy_config
from app.indicators.engine import calculate_indicators
from app.strategy.market_regime import MarketRegime
from app.strategy.strategy import StrategyEngine, TradePlan

MIN_STOCK_HISTORY_ROWS = 210
MIN_INDEX_HISTORY_ROWS = 200


def _weekly_decision_dates(
    index_history: pd.DataFrame, start: date, end: date
) -> List[date]:
    """One decision date per calendar week: the last available index trading
    date on or before that week's end, mirroring the plan's weekend scan.
    """
    in_range = sorted(
        d for d in index_history["timestamp"].unique() if start <= d <= end
    )
    by_week: Dict[Tuple[int, int], date] = {}
    for d in in_range:
        iso_year, iso_week, _ = d.isocalendar()
        by_week[(iso_year, iso_week)] = d  # ascending order -> last date wins
    return sorted(by_week.values())


def run_backtest(
    stock_history: Dict[str, pd.DataFrame],
    index_history: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> List[TradeResult]:
    """Event-driven weekly walk-forward backtest.

    For every decision date T, each symbol's history is truncated to rows
    with timestamp <= T before indicators are recalculated, so nothing after
    T can influence the signal (no look-ahead bias). A selected candidate's
    outcome is then resolved from the candles strictly after T. A symbol
    with an open simulated position is skipped for new signals until it
    exits, and the number of concurrently open trades is capped at
    `portfolio.max_positions`.

    Indicators are recomputed from scratch on a growing slice for every
    symbol at every decision date; this trades runtime for correctness and
    simplicity, which is the right tradeoff for an offline research
    backtest over a modest universe.
    """
    config = get_strategy_config()
    decision_dates = _weekly_decision_dates(index_history, start_date, end_date)

    open_positions: Dict[str, date] = {}
    trades: List[TradeResult] = []

    for decision_date in decision_dates:
        open_positions = {
            sym: exit_dt
            for sym, exit_dt in open_positions.items()
            if exit_dt > decision_date
        }
        open_slots = config.portfolio.max_positions - len(open_positions)
        if open_slots <= 0:
            continue

        index_slice = index_history[index_history["timestamp"] <= decision_date]
        if len(index_slice) < MIN_INDEX_HISTORY_ROWS:
            continue
        index_slice = calculate_indicators(index_slice)
        regime = MarketRegime.determine(index_slice.iloc[-1]).value

        candidates: List[Tuple[TradePlan, pd.DataFrame]] = []
        for symbol, history in stock_history.items():
            if symbol in open_positions:
                continue

            history_slice = history[history["timestamp"] <= decision_date]
            if len(history_slice) < MIN_STOCK_HISTORY_ROWS:
                continue

            indicators = calculate_indicators(history_slice, index_slice)
            latest = indicators.iloc[-1]

            plan = StrategyEngine.evaluate_candidate(latest, regime, symbol=symbol)
            if plan is None:
                continue

            future_candles = history[history["timestamp"] > decision_date]
            candidates.append((plan, future_candles))

        candidates.sort(key=lambda c: c[0].score, reverse=True)
        selected = candidates[:open_slots]

        for plan, future_candles in selected:
            result = simulate_trade(plan, decision_date, future_candles)
            trades.append(result)
            if result.exit_date is not None:
                open_positions[plan.symbol] = result.exit_date

    return trades
