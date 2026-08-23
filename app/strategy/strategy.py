from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from app.core.config import get_strategy_config
from app.risk.position_sizing import PositionSizer
from app.risk.risk_rules import RiskRules
from app.strategy.filters import HardFilters
from app.strategy.scoring import ScoringEngine
from app.strategy.setup_detector import SetupDetector


@dataclass
class TradePlan:
    symbol: str
    setup_type: str
    score: float
    current_price: float
    entry_low: float
    entry_high: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: float
    quantity: int
    capital_required: float
    max_loss: float


class StrategyEngine:
    """Single deterministic pipeline shared by the weekly scan job and the
    backtester, so a recommendation is evaluated identically whether it is
    produced live or replayed historically.
    """

    @staticmethod
    def evaluate_candidate(
        row: pd.Series, regime: str, symbol: Optional[str] = None
    ) -> Optional[TradePlan]:
        config = get_strategy_config()
        symbol = symbol if symbol is not None else row.get("symbol", "")

        if not HardFilters.is_eligible(row):
            return None

        setup = SetupDetector.detect(row, regime)
        if not setup:
            return None

        score = ScoringEngine.score(row, setup)
        if score < config.selection.minimum_score:
            return None

        entry_low, entry_high, stop_loss, target_1, target_2 = (
            RiskRules.calculate_levels(row, setup)
        )

        quantity, capital_required, max_loss = PositionSizer.calculate(
            entry_low, stop_loss
        )
        if quantity <= 0:
            return None

        risk_reward = (
            (target_1 - entry_low) / (entry_low - stop_loss)
            if (entry_low - stop_loss) > 0
            else 0.0
        )
        if risk_reward < config.risk.min_risk_reward:
            return None

        return TradePlan(
            symbol=symbol,
            setup_type=setup,
            score=score,
            current_price=row["close"],
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=risk_reward,
            quantity=quantity,
            capital_required=capital_required,
            max_loss=max_loss,
        )

    @staticmethod
    def select_final_picks(candidates: List[TradePlan]) -> List[TradePlan]:
        config = get_strategy_config()
        ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
        return ranked[: config.selection.final_picks]
