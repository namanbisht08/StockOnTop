import sys
from datetime import date

import pandas as pd

from app.core.logging import get_logger
from app.db.models import Candle, Recommendation, ScanRun, Stock
from app.db.session import SessionLocal
from app.indicators.engine import calculate_indicators
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

        scan_run.candidate_count = len(candidates)

        final_picks = StrategyEngine.select_final_picks(candidates)
        scan_run.final_count = len(final_picks)

        for idx, plan in enumerate(final_picks):
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
            )
            db.add(rec)

        scan_run.status = "COMPLETED"
        db.commit()

        if not final_picks:
            logger.info("NO TRADE THIS WEEK")
        else:
            logger.info(f"Scan complete. Found {len(final_picks)} picks.")

    except Exception as e:
        scan_run.status = "FAILED"
        scan_run.error_message = str(e)
        db.commit()
        logger.error(f"Scan failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()
