from typing import Tuple

from app.core.config import get_strategy_config


class PositionSizer:
    @staticmethod
    def calculate(entry: float, stop_loss: float) -> Tuple[int, float, float]:
        """Returns quantity, capital_required, max_loss"""
        config = get_strategy_config()

        capital = config.portfolio.capital
        max_trade_risk = capital * (config.risk.max_risk_per_trade_pct / 100)

        risk_per_share = entry - stop_loss
        if risk_per_share <= 0:
            return 0, 0.0, 0.0

        risk_quantity = int(max_trade_risk // risk_per_share)

        max_capital_per_trade = (
            capital
            * (config.portfolio.max_portfolio_exposure_pct / 100)
            / config.portfolio.max_positions
        )
        capital_quantity = int(max_capital_per_trade // entry)

        final_quantity = min(risk_quantity, capital_quantity)

        capital_required = final_quantity * entry
        max_loss = final_quantity * risk_per_share

        return final_quantity, capital_required, max_loss
