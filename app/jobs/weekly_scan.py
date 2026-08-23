import sys
from datetime import date
from typing import Optional

import pandas as pd

from app.ai.analyzer import CandidateAnalyzer
from app.ai.provider import build_default_providers
from app.core.config import get_settings, get_strategy_config
from app.core.logging import get_logger
from app.db.models import Candle, Recommendation, ScanRun, Stock
from app.db.session import SessionLocal
from app.indicators.engine import calculate_indicators
from app.reports.generator import generate_telegram_message
from app.reports.telegram import TelegramNotificationError, TelegramNotifier
from app.strategy.market_regime import MarketRegime
from app.strategy.strategy import StrategyEngine

logger = get_logger(__name__)

INDEX_SYMBOL = "^NSEI"
MIN_HISTORY_ROWS = 200


def _load_candle_df(db, symbol: str) -> pd.DataFrame:
    candles = (
        db.query(Candle)
        .filter(Candle.symbol == symbol)
        .order_by(Candle.timestamp.asc())
        .all()
    )
    df = pd.DataFrame([c.__dict__ for c in candles])
    return df.drop("_sa_instance_state", axis=1, errors="ignore")


def _safe_float(value) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _send_telegram_report(final_picks, regime: str) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("Telegram not configured; skipping notification")
        return

    capital = get_strategy_config().portfolio.capital
    message = generate_telegram_message(final_picks, regime, capital)
    try:
        notifier = TelegramNotifier(
            settings.telegram_bot_token, settings.telegram_chat_id
        )
        notifier.send_message(message)
        logger.info("Telegram notification sent")
    except TelegramNotificationError as e:
        # A failed notification must never fail the scan itself - the
        # recommendations are already persisted (plan section 45).
        logger.error(f"Telegram notification failed: {e}")


def run_weekly_scan():
    db = SessionLocal()
    scan_run = ScanRun(status="RUNNING")
    db.add(scan_run)
    db.commit()

    try:
        stocks = db.query(Stock).filter(Stock.active).all()

        scan_run.universe_size = len(stocks)
        logger.info(f"Scanning {len(stocks)} stocks")

        index_df = _load_candle_df(db, INDEX_SYMBOL)
        if len(index_df) >= MIN_HISTORY_ROWS:
            index_df = calculate_indicators(index_df)
            regime = MarketRegime.determine(index_df.iloc[-1]).value
        else:
            logger.warning(
                f"Insufficient index history ({len(index_df)} rows) for "
                f"{INDEX_SYMBOL}; defaulting regime to NEUTRAL"
            )
            regime = "NEUTRAL"
            index_df = None
        scan_run.market_regime = regime

        candidates = []
        indicators_by_symbol = {}

        for stock in stocks:
            df = _load_candle_df(db, stock.symbol)
            if len(df) < MIN_HISTORY_ROWS:
                logger.info(f"{stock.symbol}: Not enough candles ({len(df)})")
                continue

            df = calculate_indicators(df, index_df)
            latest = df.iloc[-1]

            plan = StrategyEngine.evaluate_candidate(latest, regime, stock.symbol)
            if plan is None:
                logger.debug(f"{stock.symbol}: No qualifying trade plan")
                continue

            candidates.append(plan)
            indicators_by_symbol[plan.symbol] = {
                "rsi14": _safe_float(latest.get("rsi14")),
                "adx": _safe_float(latest.get("adx")),
                "relative_volume": _safe_float(latest.get("relative_volume")),
                "relative_strength_20d": _safe_float(
                    latest.get("relative_strength_20d")
                ),
                "relative_strength_60d": _safe_float(
                    latest.get("relative_strength_60d")
                ),
            }

        scan_run.candidate_count = len(candidates)

        final_picks = StrategyEngine.select_final_picks(candidates)
        scan_run.final_count = len(final_picks)

        analyzer = CandidateAnalyzer(build_default_providers())

        for idx, plan in enumerate(final_picks):
            analysis = analyzer.analyze(
                plan,
                indicators=indicators_by_symbol.get(plan.symbol, {}),
                news_headlines=[],  # news provider integration is not built yet
                market_regime=regime,
            )
            if analysis.ai_status != "ok":
                logger.info(f"{plan.symbol}: AI explanation unavailable")

            rec = Recommendation(
                run_id=scan_run.id,
                symbol=plan.symbol,
                recommendation_date=date.today(),
                setup_type=plan.setup_type,
                score=plan.score,
                rank=idx + 1,
                market_regime=regime,
                current_price=plan.current_price,
                entry_low=plan.entry_low,
                entry_high=plan.entry_high,
                stop_loss=plan.stop_loss,
                target_1=plan.target_1,
                target_2=plan.target_2,
                risk_reward=plan.risk_reward,
                quantity=plan.quantity,
                capital_required=plan.capital_required,
                max_loss=plan.max_loss,
                status="WATCHLIST",
                ai_explanation=(
                    analysis.explanation.model_dump_json()
                    if analysis.explanation
                    else None
                ),
            )
            db.add(rec)

        scan_run.status = "COMPLETED"
        db.commit()

        if not final_picks:
            logger.info("NO TRADE THIS WEEK")
        else:
            logger.info(f"Scan complete. Found {len(final_picks)} picks.")

        _send_telegram_report(final_picks, regime)

    except Exception as e:
        scan_run.status = "FAILED"
        scan_run.error_message = str(e)
        db.commit()
        logger.error(f"Scan failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()
