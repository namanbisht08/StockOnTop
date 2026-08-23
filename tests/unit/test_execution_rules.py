from datetime import date

import pandas as pd

from app.strategy.execution_rules import (
    EXIT_STOPPED_OUT,
    EXIT_TARGET_1_HIT,
    check_entry_fill,
    check_exit,
    search_entry_fill,
    search_exit,
)


def _candle(open_, high, low, close, timestamp=None):
    return pd.Series(
        {
            "timestamp": timestamp,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        }
    )


def test_check_entry_fill_clamps_open_into_zone():
    candle = _candle(100.5, 101.0, 100.0, 100.8)
    result = check_entry_fill(
        candle, entry_low=100.0, entry_high=101.0, extended_entry_pct=3.0
    )
    assert result.filled
    assert result.price == 100.5
    assert not result.expired


def test_check_entry_fill_gap_open_below_zone_fills_at_entry_low():
    candle = _candle(99.0, 100.5, 98.5, 100.2)
    result = check_entry_fill(
        candle, entry_low=100.0, entry_high=101.0, extended_entry_pct=3.0
    )
    assert result.filled
    assert result.price == 100.0


def test_check_entry_fill_no_overlap_is_not_filled_or_expired():
    candle = _candle(95.0, 96.0, 94.0, 95.5)
    result = check_entry_fill(
        candle, entry_low=100.0, entry_high=101.0, extended_entry_pct=3.0
    )
    assert not result.filled
    assert not result.expired


def test_check_entry_fill_extended_gap_is_expired():
    # entry_high=101, extended_entry_pct=3 -> limit 104.03
    candle = _candle(110.0, 112.0, 105.0, 111.0)
    result = check_entry_fill(
        candle, entry_low=100.0, entry_high=101.0, extended_entry_pct=3.0
    )
    assert not result.filled
    assert result.expired


def test_check_exit_stop_takes_priority_over_target():
    candle = _candle(100.0, 120.0, 80.0, 100.0)  # range spans both stop and target
    result = check_exit(candle, stop_loss=95.0, target_1=110.0)
    assert result.exited
    assert result.reason == EXIT_STOPPED_OUT


def test_check_exit_target_hit():
    candle = _candle(105.0, 112.0, 104.0, 111.0)
    result = check_exit(candle, stop_loss=95.0, target_1=110.0)
    assert result.exited
    assert result.reason == EXIT_TARGET_1_HIT
    assert result.price == 110.0  # open (105) below target, so fills at target


def test_check_exit_no_hit():
    candle = _candle(100.0, 102.0, 99.0, 101.0)
    result = check_exit(candle, stop_loss=95.0, target_1=110.0)
    assert not result.exited


def test_search_entry_fill_finds_fill_within_window():
    candles = pd.DataFrame(
        [
            {
                "timestamp": date(2024, 1, 1),
                "open": 90,
                "high": 91,
                "low": 89,
                "close": 90.5,
            },
            {
                "timestamp": date(2024, 1, 2),
                "open": 100.5,
                "high": 101,
                "low": 100,
                "close": 100.8,
            },
        ]
    )
    filled, price, pos, days_scanned = search_entry_fill(
        candles, 100.0, 101.0, 3.0, max_days=5
    )
    assert filled
    assert price == 100.5
    assert pos == 1
    assert days_scanned == 2


def test_search_entry_fill_unresolved_within_short_window():
    candles = pd.DataFrame(
        [
            {
                "timestamp": date(2024, 1, 1),
                "open": 90,
                "high": 91,
                "low": 89,
                "close": 90.5,
            }
        ]
    )
    filled, price, pos, days_scanned = search_entry_fill(
        candles, 100.0, 101.0, 3.0, max_days=5
    )
    assert not filled
    assert price is None
    assert days_scanned == 1  # caller decides if that's "still waiting" or "expired"


def test_search_entry_fill_stops_scanning_on_expiry():
    candles = pd.DataFrame(
        [
            {
                "timestamp": date(2024, 1, 1),
                "open": 110,
                "high": 112,
                "low": 105,
                "close": 111,
            },
            {
                "timestamp": date(2024, 1, 2),
                "open": 100.5,
                "high": 101,
                "low": 100,
                "close": 100.8,
            },
        ]
    )
    filled, price, pos, days_scanned = search_entry_fill(
        candles, 100.0, 101.0, 3.0, max_days=5
    )
    assert not filled
    assert days_scanned == 1  # never looks at day 2 once gapped away


def test_search_exit_finds_target_within_window():
    candles = pd.DataFrame(
        [
            {
                "timestamp": date(2024, 1, 1),
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
            },
            {
                "timestamp": date(2024, 1, 2),
                "open": 105,
                "high": 112,
                "low": 104,
                "close": 111,
            },
        ]
    )
    reason, price, pos, days_scanned = search_exit(candles, 95.0, 110.0, max_days=20)
    assert reason == EXIT_TARGET_1_HIT
    assert pos == 1
    assert days_scanned == 2


def test_search_exit_unresolved_returns_days_scanned():
    candles = pd.DataFrame(
        [
            {
                "timestamp": date(2024, 1, 1),
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
            }
        ]
    )
    reason, price, pos, days_scanned = search_exit(candles, 95.0, 110.0, max_days=20)
    assert reason is None
    assert days_scanned == 1
