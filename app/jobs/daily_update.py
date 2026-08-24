import sys
from datetime import date, datetime, timedelta
from typing import Dict, List

import pandas as pd

from app.backtest.simulator import calculate_charges
from app.core.config import get_settings, get_strategy_config
from app.core.logging import get_logger
from app.data.yahoo_finance import YahooFinanceProvider
from app.db.models import DailyUpdateRun, Recommendation, RecommendationOutcome
from app.db.session import SessionLocal
from app.reports.generator import generate_daily_status_message
from app.reports.telegram import TelegramNotificationError, TelegramNotifier
from app.strategy.execution_rules import search_entry_fill, search_exit

logger = get_logger(__name__)

OPEN_STATUSES = ("ENTRY_PENDING", "ACTIVE")
# TIME_EXIT isn't part of the plan's status vocabulary (WATCHLIST,
# ENTRY_PENDING, ACTIVE, TARGET_1_HIT, TARGET_2_HIT, STOPPED_OUT, EXPIRED,
# REJECTED) - map it onto EXPIRED for the persisted Recommendation.status
# while keeping the more specific "TIME_EXIT" in RecommendationOutcome.exit_reason.
STATUS_FOR_EXIT_REASON = {
    "STOPPED_OUT": "STOPPED_OUT",
    "TARGET_1_HIT": "TARGET_1_HIT",
    "TIME_EXIT": "EXPIRED",
}


def _already_completed_today(db) -> bool:
    return (
        db.query(DailyUpdateRun).filter(DailyUpdateRun.run_date == date.today()).first()
        is not None
    )


def _fetch_candles_after(provider, symbol: str, since: date) -> pd.DataFrame:
    """Candles strictly after `since`, up to today - a wider lookback than
    "just yesterday" so a missed run (instance downtime, etc.) is caught up
    on the next run rather than silently skipping days.
    """
    # yfinance's `end` is exclusive, so today's own candle (already closed by
    # the time this job runs in the evening) would otherwise be dropped -
    # this caused every open position to report "no new data yet" even when
    # today's close had already crossed the entry zone.
    end = date.today() + timedelta(days=1)
    start = since - timedelta(days=5)
    df = provider.get_ohlcv(symbol, start, end)
    if df.empty:
        return df
    return df[df["timestamp"] > since].reset_index(drop=True)


def _apply_exit(
    rec: Recommendation,
    outcome: RecommendationOutcome,
    reason: str,
    exit_price_raw: float,
    exit_date,
    holding_days: int,
    costs,
) -> Dict:
    exit_price = exit_price_raw * (1 - costs.slippage_pct / 100)
    buy_value = outcome.entry_price * rec.quantity
    sell_value = exit_price * rec.quantity
    charges = calculate_charges(buy_value, sell_value, costs)
    gross_pnl = sell_value - buy_value
    net_pnl = gross_pnl - charges

    outcome.exit_price = exit_price
    outcome.exit_date = exit_date
    outcome.exit_reason = reason
    outcome.gross_pnl = gross_pnl
    outcome.charges = charges
    outcome.net_pnl = net_pnl
    outcome.return_pct = (net_pnl / buy_value * 100) if buy_value > 0 else 0.0
    outcome.holding_days = holding_days

    rec.status = STATUS_FOR_EXIT_REASON.get(reason, reason)

    return {
        "symbol": rec.symbol,
        "status": reason,
        "detail": f"exit at Rs.{exit_price:,.2f}, net P&L Rs.{net_pnl:,.2f}",
        "entry_price": outcome.entry_price,
        "current_price": exit_price,
        "quantity": rec.quantity,
        "stop_loss": rec.stop_loss,
        "target_1": rec.target_1,
        "target_2": rec.target_2,
        "net_pnl": net_pnl,
    }


def _resolve_entry_pending(
    rec: Recommendation, provider, backtest_config, costs
) -> Dict:
    candles = _fetch_candles_after(provider, rec.symbol, rec.recommendation_date)
    if candles.empty:
        return {
            "symbol": rec.symbol,
            "status": "STILL_WATCHING",
            "detail": "no new data yet",
        }

    filled, price, pos, days_scanned = search_entry_fill(
        candles,
        rec.entry_low,
        rec.entry_high,
        backtest_config.extended_entry_pct,
        backtest_config.entry_expiry_days,
    )

    if filled:
        entry_price = price * (1 + costs.slippage_pct / 100)
        entry_date = candles.iloc[pos]["timestamp"]
        rec.status = "ACTIVE"
        outcome = rec.outcome or RecommendationOutcome(recommendation_id=rec.id)
        outcome.entry_price = entry_price
        outcome.entry_date = entry_date
        rec.outcome = outcome

        # The fill and an exit can land in the same batch of candles (e.g. a
        # same-day stop-out) - check onward from the entry day itself rather
        # than waiting for tomorrow's run to notice.
        candles_since_entry = candles.iloc[pos:].reset_index(drop=True)
        reason, exit_price_raw, exit_pos, holding_days = search_exit(
            candles_since_entry,
            rec.stop_loss,
            rec.target_1,
            backtest_config.max_holding_days,
        )
        if reason is not None:
            exit_date = candles_since_entry.iloc[exit_pos]["timestamp"]
            return _apply_exit(
                rec, outcome, reason, exit_price_raw, exit_date, holding_days, costs
            )
        if holding_days >= backtest_config.max_holding_days:
            last_candle = candles_since_entry.iloc[holding_days - 1]
            return _apply_exit(
                rec,
                outcome,
                "TIME_EXIT",
                last_candle["close"],
                last_candle["timestamp"],
                holding_days,
                costs,
            )

        current_price = candles_since_entry.iloc[-1]["close"]
        return {
            "symbol": rec.symbol,
            "status": "ENTERED",
            "detail": f"filled at Rs.{entry_price:,.2f}",
            "entry_price": entry_price,
            "current_price": current_price,
            "quantity": rec.quantity,
            "stop_loss": rec.stop_loss,
            "target_1": rec.target_1,
            "target_2": rec.target_2,
        }

    if days_scanned >= backtest_config.entry_expiry_days:
        rec.status = "EXPIRED"
        return {
            "symbol": rec.symbol,
            "status": "EXPIRED_NO_FILL",
            "detail": f"never entered the zone within {backtest_config.entry_expiry_days} days",
        }

    return {
        "symbol": rec.symbol,
        "status": "STILL_WATCHING",
        "detail": f"day {days_scanned} of {backtest_config.entry_expiry_days}",
    }


def _resolve_active(rec: Recommendation, provider, backtest_config, costs) -> Dict:
    outcome = rec.outcome
    candles = _fetch_candles_after(provider, rec.symbol, outcome.entry_date)
    if candles.empty:
        return {"symbol": rec.symbol, "status": "HOLD", "detail": "no new data yet"}

    reason, price, pos, holding_days = search_exit(
        candles, rec.stop_loss, rec.target_1, backtest_config.max_holding_days
    )

    if reason is None:
        if holding_days < backtest_config.max_holding_days:
            return {
                "symbol": rec.symbol,
                "status": "HOLD",
                "detail": f"day {holding_days} of {backtest_config.max_holding_days}",
                "entry_price": outcome.entry_price,
                "current_price": candles.iloc[-1]["close"],
                "quantity": rec.quantity,
                "stop_loss": rec.stop_loss,
                "target_1": rec.target_1,
                "target_2": rec.target_2,
            }
        last_candle = candles.iloc[holding_days - 1]
        return _apply_exit(
            rec,
            outcome,
            "TIME_EXIT",
            last_candle["close"],
            last_candle["timestamp"],
            holding_days,
            costs,
        )

    exit_date = candles.iloc[pos]["timestamp"]
    return _apply_exit(rec, outcome, reason, price, exit_date, holding_days, costs)


def _send_daily_digest(digest: List[Dict]) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("Telegram not configured; skipping daily digest")
        return
    if not digest:
        return

    message = generate_daily_status_message(digest)
    try:
        notifier = TelegramNotifier(
            settings.telegram_bot_token, settings.telegram_chat_id
        )
        notifier.send_message(message, parse_mode="HTML")
        logger.info("Daily digest sent")
    except TelegramNotificationError as e:
        logger.error(f"Daily digest failed to send: {e}")


def run_daily_update():
    db = SessionLocal()

    if _already_completed_today(db):
        logger.info("Daily update already completed today; skipping duplicate run")
        db.close()
        return

    run = DailyUpdateRun(run_date=date.today(), status="RUNNING")
    db.add(run)
    db.commit()

    try:
        provider = YahooFinanceProvider()
        strategy_config = get_strategy_config()
        backtest_config = strategy_config.backtest
        costs = strategy_config.costs

        open_recs = (
            db.query(Recommendation)
            .filter(Recommendation.status.in_(OPEN_STATUSES))
            .all()
        )

        digest = []
        for rec in open_recs:
            try:
                if rec.status == "ENTRY_PENDING":
                    result = _resolve_entry_pending(
                        rec, provider, backtest_config, costs
                    )
                else:
                    result = _resolve_active(rec, provider, backtest_config, costs)
                digest.append(result)
            except Exception as e:
                logger.error(f"{rec.symbol}: daily update failed: {e}", exc_info=True)
                digest.append(
                    {"symbol": rec.symbol, "status": "ERROR", "detail": str(e)}
                )

        db.commit()

        run.positions_checked = len(open_recs)
        run.status = "COMPLETED"
        run.completed_at = datetime.utcnow()
        db.commit()

        logger.info(f"Daily update complete. Checked {len(open_recs)} open positions.")
        _send_daily_digest(digest)

    except Exception as e:
        run.status = "FAILED"
        run.error_message = str(e)
        db.commit()
        logger.error(f"Daily update failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()
