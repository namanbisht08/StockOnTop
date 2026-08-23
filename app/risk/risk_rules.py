from typing import Tuple

import pandas as pd

from app.core.config import get_strategy_config


class RiskRules:
    @staticmethod
    def calculate_levels(
        row: pd.Series, setup: str
    ) -> Tuple[float, float, float, float, float]:
        """Returns entry_low, entry_high, stop_loss, target_1, target_2"""
        config = get_strategy_config().risk

        close = row["close"]
        atr = row.get("atr14", close * 0.02)

        entry_low = close
        entry_high = close * 1.01

        # Stop loss calculation
        atr_stop = entry_low - (atr * 1.5)
        tech_stop = row.get("sma50", entry_low * 0.95)

        stop_loss = max(atr_stop, tech_stop)

        # Constraints on stop loss
        max_sl = entry_low * (1 - config.max_stop_loss_pct / 100)
        min_sl = entry_low * (1 - config.min_stop_loss_pct / 100)

        if stop_loss < max_sl:
            stop_loss = max_sl
        if stop_loss > min_sl:
            stop_loss = min_sl

        risk_per_share = entry_low - stop_loss

        target_1 = entry_low + (risk_per_share * config.min_risk_reward)
        target_2 = entry_low + (risk_per_share * config.min_risk_reward * 1.5)

        return entry_low, entry_high, stop_loss, target_1, target_2
