from datetime import date, timedelta

import pandas as pd
import pytest

from app.backtest.simulator import calculate_charges, simulate_trade
from app.core.config import CostsConfig, get_strategy_config
from app.strategy.strategy import TradePlan

SIGNAL_DATE = date(2024, 1, 5)


def _plan(**overrides) -> TradePlan:
    defaults = {
        "symbol": "TEST",
        "setup_type": "BREAKOUT",
        "score": 80.0,
        "current_price": 100.0,
        "entry_low": 100.0,
        "entry_high": 101.0,
        "stop_loss": 95.0,
        "target_1": 110.0,
        "target_2": 115.0,
        "risk_reward": 2.0,
        "quantity": 10,
        "capital_required": 1000.0,
        "max_loss": 50.0,
    }
    defaults.update(overrides)
    return TradePlan(**defaults)


def _candles(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])


def test_calculate_charges_matches_hand_computed_formula():
    costs = CostsConfig(
        brokerage_pct=0.03,
        brokerage_max=20.0,
        stt_sell_pct=0.025,
        exchange_txn_pct=0.00297,
        gst_pct=18.0,
        sebi_charges_pct=0.0001,
        stamp_duty_buy_pct=0.015,
        slippage_pct=0.05,
    )
    buy_value, sell_value = 10_000.0, 11_000.0

    buy_brokerage = min(buy_value * 0.03 / 100, 20.0)
    sell_brokerage = min(sell_value * 0.03 / 100, 20.0)
    exchange_txn = (buy_value + sell_value) * 0.00297 / 100
    stt = sell_value * 0.025 / 100
    stamp_duty = buy_value * 0.015 / 100
    sebi_charges = (buy_value + sell_value) * 0.0001 / 100
    gst = (buy_brokerage + sell_brokerage + exchange_txn) * 18.0 / 100
    expected = (
        buy_brokerage
        + sell_brokerage
        + exchange_txn
        + stt
        + stamp_duty
        + sebi_charges
        + gst
    )

    assert calculate_charges(buy_value, sell_value, costs) == pytest.approx(expected)


def test_calculate_charges_caps_brokerage_at_max():
    costs = CostsConfig(brokerage_pct=1.0, brokerage_max=20.0)
    # 1% of 100,000 would be 1000, capped to 20
    charges_with_cap = calculate_charges(100_000.0, 0.0, costs)
    costs_uncapped = CostsConfig(brokerage_pct=1.0, brokerage_max=0.0)
    charges_uncapped = calculate_charges(100_000.0, 0.0, costs_uncapped)
    assert charges_with_cap < charges_uncapped


def test_simulate_trade_target_hit():
    plan = _plan()
    candles = _candles(
        [
            (date(2024, 1, 8), 100.5, 101.0, 100.0, 100.8),  # fills entry
            (date(2024, 1, 9), 105.0, 112.0, 104.0, 111.0),  # hits target_1
        ]
    )

    result = simulate_trade(plan, SIGNAL_DATE, candles)
    costs = get_strategy_config().costs

    expected_entry = 100.5 * (1 + costs.slippage_pct / 100)
    expected_exit = 110.0 * (1 - costs.slippage_pct / 100)  # open(105) < target

    assert result.exit_reason == "TARGET_1_HIT"
    assert result.entry_date == date(2024, 1, 8)
    assert result.exit_date == date(2024, 1, 9)
    assert result.holding_days == 2
    assert result.entry_price == pytest.approx(expected_entry)
    assert result.exit_price == pytest.approx(expected_exit)

    expected_charges = calculate_charges(
        expected_entry * plan.quantity, expected_exit * plan.quantity, costs
    )
    expected_net_pnl = (
        expected_exit * plan.quantity
        - expected_entry * plan.quantity
        - expected_charges
    )
    assert result.net_pnl == pytest.approx(expected_net_pnl)


def test_simulate_trade_stop_hit_intraday():
    plan = _plan()
    candles = _candles(
        [
            (date(2024, 1, 8), 100.5, 101.0, 100.0, 100.6),  # fills entry
            (date(2024, 1, 9), 99.0, 100.0, 90.0, 91.0),  # breaches stop intraday
        ]
    )

    result = simulate_trade(plan, SIGNAL_DATE, candles)

    assert result.exit_reason == "STOPPED_OUT"
    assert result.exit_date == date(2024, 1, 9)
    # open (99) is above stop_loss (95), so fill is at the stop level itself
    costs = get_strategy_config().costs
    assert result.exit_price == pytest.approx(95.0 * (1 - costs.slippage_pct / 100))


def test_simulate_trade_stop_hit_on_gap_down():
    plan = _plan()
    candles = _candles(
        [
            (date(2024, 1, 8), 100.5, 101.0, 100.0, 100.6),
            (date(2024, 1, 9), 90.0, 91.0, 88.0, 89.0),  # gaps below the stop
        ]
    )
    result = simulate_trade(plan, SIGNAL_DATE, candles)
    costs = get_strategy_config().costs

    assert result.exit_reason == "STOPPED_OUT"
    assert result.exit_price == pytest.approx(90.0 * (1 - costs.slippage_pct / 100))


def test_simulate_trade_no_fill_on_extended_gap():
    plan = _plan()  # entry_high=101, extended_entry_pct default 3.0 -> limit 104.03
    candles = _candles(
        [
            (date(2024, 1, 8), 110.0, 112.0, 105.0, 111.0),  # gapped past the limit
        ]
    )

    result = simulate_trade(plan, SIGNAL_DATE, candles)

    assert result.exit_reason == "NO_FILL"
    assert result.entry_date is None
    assert result.quantity == 0
    assert result.net_pnl == 0.0


def test_simulate_trade_time_exit_when_more_data_remains():
    plan = _plan()
    candles = _candles(
        [(date(2024, 1, 8), 100.5, 101.0, 100.0, 100.6)]  # entry day
        + [
            (date(2024, 1, 9) + timedelta(days=i), 102.0, 103.0, 101.0, 102.0)
            for i in range(24)  # flat, no stop/target
        ]
    )

    result = simulate_trade(plan, SIGNAL_DATE, candles)

    assert result.exit_reason == "TIME_EXIT"
    assert result.holding_days == get_strategy_config().backtest.max_holding_days


def test_simulate_trade_end_of_data_when_history_runs_out():
    plan = _plan()
    candles = _candles(
        [(date(2024, 1, 8), 100.5, 101.0, 100.0, 100.6)]
        + [
            (date(2024, 1, 9) + timedelta(days=i), 102.0, 103.0, 101.0, 102.0)
            for i in range(4)
        ]
    )

    result = simulate_trade(plan, SIGNAL_DATE, candles)

    assert result.exit_reason == "END_OF_DATA"
    assert result.holding_days == 5
