import pandas as pd

from app.strategy.strategy import StrategyEngine, TradePlan


def _qualifying_row(**overrides) -> pd.Series:
    row = {
        "close": 200.0,
        "sma20": 195.0,
        "sma50": 190.0,
        "sma200": 170.0,
        "rsi14": 60.0,
        "adx": 30.0,
        "atr14": 4.0,
        "relative_volume": 2.5,
        "volume_sma20": 1_000_000.0,
        "relative_strength_20d": 0.05,
        "relative_strength_60d": 0.08,
    }
    row.update(overrides)
    return pd.Series(row)


def test_evaluate_candidate_returns_none_when_filters_fail():
    row = _qualifying_row(close=50.0)  # below min_price
    assert StrategyEngine.evaluate_candidate(row, "BULLISH", symbol="X") is None


def test_evaluate_candidate_returns_none_when_no_setup():
    row = _qualifying_row(close=180.0, sma50=190.0)  # close below sma50, no breakout
    assert StrategyEngine.evaluate_candidate(row, "BULLISH", symbol="X") is None


def test_evaluate_candidate_returns_trade_plan_for_qualifying_breakout():
    row = _qualifying_row()
    plan = StrategyEngine.evaluate_candidate(row, "BULLISH", symbol="XYZ")

    assert isinstance(plan, TradePlan)
    assert plan.symbol == "XYZ"
    assert plan.setup_type == "BREAKOUT"
    assert plan.quantity > 0
    assert plan.entry_low <= plan.entry_high
    assert plan.stop_loss < plan.entry_low
    assert plan.target_1 > plan.entry_low
    assert plan.risk_reward >= 2.0  # config.risk.min_risk_reward default


def test_evaluate_candidate_rejects_bearish_regime():
    row = _qualifying_row()
    assert StrategyEngine.evaluate_candidate(row, "BEARISH", symbol="XYZ") is None


def test_select_final_picks_ranks_by_score_and_truncates():
    plans = [
        TradePlan(
            symbol=f"S{i}",
            setup_type="BREAKOUT",
            score=score,
            current_price=100.0,
            entry_low=100.0,
            entry_high=101.0,
            stop_loss=95.0,
            target_1=110.0,
            target_2=115.0,
            risk_reward=2.0,
            quantity=10,
            capital_required=1000.0,
            max_loss=50.0,
        )
        for i, score in enumerate([60, 90, 75, 85])
    ]

    picks = StrategyEngine.select_final_picks(plans)

    assert [p.score for p in picks] == sorted((p.score for p in plans), reverse=True)[
        : len(picks)
    ]
    assert picks[0].score == 90
