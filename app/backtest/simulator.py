from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

from app.core.config import CostsConfig, get_strategy_config
from app.strategy.execution_rules import search_entry_fill, search_exit
from app.strategy.strategy import TradePlan


@dataclass
class TradeResult:
    symbol: str
    setup_type: str
    score: float
    signal_date: date
    entry_date: Optional[date]
    entry_price: Optional[float]
    exit_date: Optional[date]
    exit_price: Optional[float]
    exit_reason: str
    quantity: int
    gross_pnl: float
    charges: float
    net_pnl: float
    return_pct: float
    holding_days: int


def _brokerage(value: float, costs: CostsConfig) -> float:
    if value <= 0:
        return 0.0
    pct_charge = value * costs.brokerage_pct / 100
    if costs.brokerage_max > 0:
        return min(pct_charge, costs.brokerage_max)
    return pct_charge


def calculate_charges(buy_value: float, sell_value: float, costs: CostsConfig) -> float:
    buy_brokerage = _brokerage(buy_value, costs)
    sell_brokerage = _brokerage(sell_value, costs)
    exchange_txn = (buy_value + sell_value) * costs.exchange_txn_pct / 100
    stt = sell_value * costs.stt_sell_pct / 100
    stamp_duty = buy_value * costs.stamp_duty_buy_pct / 100
    sebi_charges = (buy_value + sell_value) * costs.sebi_charges_pct / 100
    gst = (buy_brokerage + sell_brokerage + exchange_txn) * costs.gst_pct / 100
    return (
        buy_brokerage
        + sell_brokerage
        + exchange_txn
        + stt
        + stamp_duty
        + sebi_charges
        + gst
    )


def _no_fill_result(plan: TradePlan, signal_date: date) -> TradeResult:
    return TradeResult(
        symbol=plan.symbol,
        setup_type=plan.setup_type,
        score=plan.score,
        signal_date=signal_date,
        entry_date=None,
        entry_price=None,
        exit_date=None,
        exit_price=None,
        exit_reason="NO_FILL",
        quantity=0,
        gross_pnl=0.0,
        charges=0.0,
        net_pnl=0.0,
        return_pct=0.0,
        holding_days=0,
    )


def simulate_trade(
    plan: TradePlan,
    signal_date: date,
    future_candles: pd.DataFrame,
) -> TradeResult:
    """Resolve a signal into an outcome using only candles strictly after
    signal_date (future_candles must already exclude the signal date itself).

    Fill/exit assumptions, documented because they materially change results:
    - Entry fills within `entry_expiry_days` trading days if a candle's range
      overlaps [entry_low, entry_high]; the fill price is the candle's open
      clamped into the zone, so a gap-open inside the zone fills at open
      rather than at entry_low.
    - A gap whose low sits beyond entry_high * (1 + extended_entry_pct/100)
      is treated as a missed entry (NO_FILL) rather than chased, mirroring
      the plan's rule against chasing an extended breakout.
    - If a single candle's range touches both the stop and target 1, the stop
      is assumed to fill first (conservative worst-case ordering).
    - Slippage worsens every fill: entry price up, exit price down.
    - The trade is fully closed at target_1 (no partial-booking toward
      target_2) - the simplest model consistent with the plan's target engine.
    """
    strategy_config = get_strategy_config()
    backtest_config = strategy_config.backtest
    costs = strategy_config.costs

    future_candles = future_candles.reset_index(drop=True)

    filled, entry_price, entry_pos, _ = search_entry_fill(
        future_candles,
        plan.entry_low,
        plan.entry_high,
        backtest_config.extended_entry_pct,
        backtest_config.entry_expiry_days,
    )
    if not filled or entry_price is None or entry_pos is None:
        # future_candles is the whole known future for this signal, so an
        # unresolved search here is definitively a missed entry - unlike the
        # live daily job, no more data will ever arrive to fill it later.
        return _no_fill_result(plan, signal_date)

    entry_date = future_candles.iloc[entry_pos]["timestamp"]
    entry_price = entry_price * (1 + costs.slippage_pct / 100)

    candles_since_entry = future_candles.iloc[entry_pos:].reset_index(drop=True)
    exit_reason, exit_price, exit_pos, holding_days = search_exit(
        candles_since_entry,
        plan.stop_loss,
        plan.target_1,
        backtest_config.max_holding_days,
    )

    if exit_reason is None:
        last_candle = candles_since_entry.iloc[holding_days - 1]
        exit_price = last_candle["close"]
        exit_date = last_candle["timestamp"]
        ran_out_of_data = holding_days < backtest_config.max_holding_days
        exit_reason = "END_OF_DATA" if ran_out_of_data else "TIME_EXIT"
    else:
        exit_date = candles_since_entry.iloc[exit_pos]["timestamp"]

    assert exit_reason is not None and exit_price is not None  # set above
    exit_price = exit_price * (1 - costs.slippage_pct / 100)

    buy_value = entry_price * plan.quantity
    sell_value = exit_price * plan.quantity
    charges = calculate_charges(buy_value, sell_value, costs)
    gross_pnl = sell_value - buy_value
    net_pnl = gross_pnl - charges
    return_pct = (net_pnl / buy_value * 100) if buy_value > 0 else 0.0

    return TradeResult(
        symbol=plan.symbol,
        setup_type=plan.setup_type,
        score=plan.score,
        signal_date=signal_date,
        entry_date=entry_date,
        entry_price=entry_price,
        exit_date=exit_date,
        exit_price=exit_price,
        exit_reason=exit_reason,
        quantity=plan.quantity,
        gross_pnl=gross_pnl,
        charges=charges,
        net_pnl=net_pnl,
        return_pct=return_pct,
        holding_days=holding_days,
    )
