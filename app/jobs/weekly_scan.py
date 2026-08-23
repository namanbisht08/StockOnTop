import sys
from datetime import date

import pandas as pd

from app.core.config import get_strategy_config
from app.core.logging import get_logger
from app.db.models import Candle, Recommendation, ScanRun, Stock
from app.db.session import SessionLocal
from app.indicators.engine import calculate_indicators
from app.risk.position_sizing import PositionSizer
from app.risk.risk_rules import RiskRules
from app.strategy.filters import HardFilters
from app.strategy.market_regime import MarketRegimeType
from app.strategy.scoring import ScoringEngine
from app.strategy.setup_detector import SetupDetector

logger = get_logger(__name__)


def run_weekly_scan():
    db = SessionLocal()
    scan_run = ScanRun(status="RUNNING")
    db.add(scan_run)
    db.commit()

    try:
        config = get_strategy_config()
        stocks = db.query(Stock).filter(Stock.active).all()

        scan_run.universe_size = len(stocks)
        logger.info(f"Scanning {len(stocks)} stocks")

        # Determine Market Regime
        regime = MarketRegimeType.BULLISH.value
        scan_run.market_regime = regime

        candidates = []

        for stock in stocks:
            candles = (
                db.query(Candle)
                .filter(Candle.symbol == stock.symbol)
                .order_by(Candle.timestamp.asc())
                .all()
            )
            if len(candles) < 200:
                logger.info(f"{stock.symbol}: Not enough candles ({len(candles)})")
                continue

            df = pd.DataFrame([c.__dict__ for c in candles])
            df = df.drop("_sa_instance_state", axis=1, errors="ignore")

            df = calculate_indicators(df)
            latest = df.iloc[-1]

            if not HardFilters.is_eligible(latest):
                logger.debug(f"{stock.symbol}: Failed hard filters")
                continue

            setup = SetupDetector.detect(latest, regime)
            if not setup:
                logger.debug(f"{stock.symbol}: No setup detected")
                continue

            score = ScoringEngine.score(latest, setup)
            if score < config.selection.minimum_score:
                logger.debug(f"{stock.symbol}: Score {score} below minimum")
                continue

            e_low, e_high, sl, t1, t2 = RiskRules.calculate_levels(latest, setup)
            qty, cap_req, max_loss = PositionSizer.calculate(e_low, sl)

            if qty == 0:
                logger.debug(f"{stock.symbol}: Quantity 0")
                continue

            rr = (t1 - e_low) / (e_low - sl) if (e_low - sl) > 0 else 0
            if rr < config.risk.min_risk_reward:
                logger.debug(f"{stock.symbol}: Risk Reward {rr} below minimum")
                continue

            candidates.append(
                {
                    "symbol": stock.symbol,
                    "score": score,
                    "setup": setup,
                    "latest": latest,
                    "risk": (e_low, e_high, sl, t1, t2, rr, qty, cap_req, max_loss),
                }
            )

        scan_run.candidate_count = len(candidates)

        candidates.sort(key=lambda x: x["score"], reverse=True)
        final_picks = candidates[: config.selection.final_picks]

        scan_run.final_count = len(final_picks)

        for idx, pick in enumerate(final_picks):
            rec = Recommendation(
                run_id=scan_run.id,
                symbol=pick["symbol"],
                recommendation_date=date.today(),
                setup_type=pick["setup"],
                score=pick["score"],
                rank=idx + 1,
                market_regime=regime,
                current_price=pick["latest"]["close"],
                entry_low=pick["risk"][0],
                entry_high=pick["risk"][1],
                stop_loss=pick["risk"][2],
                target_1=pick["risk"][3],
                target_2=pick["risk"][4],
                risk_reward=pick["risk"][5],
                quantity=pick["risk"][6],
                capital_required=pick["risk"][7],
                max_loss=pick["risk"][8],
                status="WATCHLIST",
            )
            db.add(rec)

        scan_run.status = "COMPLETED"
        db.commit()

        logger.info(f"Scan complete. Found {len(final_picks)} picks.")

    except Exception as e:
        scan_run.status = "FAILED"
        scan_run.error_message = str(e)
        db.commit()
        logger.error(f"Scan failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()
