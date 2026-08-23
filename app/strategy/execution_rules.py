from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd

EXIT_STOPPED_OUT = "STOPPED_OUT"
EXIT_TARGET_1_HIT = "TARGET_1_HIT"


@dataclass
class FillResult:
    filled: bool
    price: Optional[float]
    expired: bool  # gapped beyond the extended limit - give up on this signal


@dataclass
class ExitResult:
    exited: bool
    price: Optional[float]
    reason: Optional[str]  # EXIT_STOPPED_OUT or EXIT_TARGET_1_HIT


def check_entry_fill(
    candle: pd.Series,
    entry_low: float,
    entry_high: float,
    extended_entry_pct: float,
) -> FillResult:
    """Shared by the backtester and the live daily job so a signal resolves
    identically either way (plan's reproducibility principle).

    A gap-open inside the zone fills at open rather than at entry_low; a gap
    whose low sits beyond entry_high * (1 + extended_entry_pct/100) is a
    permanently missed entry rather than something to keep chasing.
    """
    extended_limit = entry_high * (1 + extended_entry_pct / 100)
    if candle["low"] > extended_limit:
        return FillResult(filled=False, price=None, expired=True)

    overlaps = candle["low"] <= entry_high and candle["high"] >= entry_low
    if overlaps:
        price = min(max(candle["open"], entry_low), entry_high)
        return FillResult(filled=True, price=price, expired=False)

    return FillResult(filled=False, price=None, expired=False)


def check_exit(candle: pd.Series, stop_loss: float, target_1: float) -> ExitResult:
    """If a single candle's range touches both the stop and target 1, the
    stop is assumed to fill first (conservative worst-case ordering).
    """
    if candle["low"] <= stop_loss:
        return ExitResult(
            exited=True, price=min(candle["open"], stop_loss), reason=EXIT_STOPPED_OUT
        )
    if candle["high"] >= target_1:
        return ExitResult(
            exited=True, price=max(candle["open"], target_1), reason=EXIT_TARGET_1_HIT
        )
    return ExitResult(exited=False, price=None, reason=None)


def search_entry_fill(
    candles: pd.DataFrame,
    entry_low: float,
    entry_high: float,
    extended_entry_pct: float,
    max_days: int,
) -> Tuple[bool, Optional[float], Optional[int], int]:
    """Scan up to max_days candles (ascending, starting the day after the
    signal) for a fill. Returns (filled, price, pos, days_scanned).

    Used by both the backtester (candles = the whole known future - a
    `days_scanned` short of max_days there means the signal is definitively
    unfillable) and the live daily job (candles = what's arrived so far - the
    same shortfall there just means "not enough days have elapsed yet, check
    again tomorrow"). The caller decides which of those two it is.
    """
    for pos in range(min(max_days, len(candles))):
        candle = candles.iloc[pos]
        fill = check_entry_fill(candle, entry_low, entry_high, extended_entry_pct)
        if fill.expired:
            return False, None, None, pos + 1
        if fill.filled:
            return True, fill.price, pos, pos + 1
    return False, None, None, min(max_days, len(candles))


def search_exit(
    candles: pd.DataFrame,
    stop_loss: float,
    target_1: float,
    max_days: int,
) -> Tuple[Optional[str], Optional[float], Optional[int], int]:
    """Scan up to max_days candles (ascending, starting the entry day) for a
    stop or target hit. Returns (reason, price, pos, days_scanned); reason is
    None if unresolved within the scanned candles - same caller-dependent
    interpretation as search_entry_fill above.
    """
    for pos in range(min(max_days, len(candles))):
        candle = candles.iloc[pos]
        exit_check = check_exit(candle, stop_loss, target_1)
        if exit_check.exited:
            return exit_check.reason, exit_check.price, pos, pos + 1
    return None, None, None, min(max_days, len(candles))
