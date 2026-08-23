import json
from typing import Dict, List

from app.strategy.strategy import TradePlan

RESPONSE_SCHEMA_INSTRUCTIONS = """
Respond with ONLY a JSON object matching exactly this shape (no markdown fences):
{
  "summary": "<one short paragraph>",
  "bullish_factors": ["<short phrase>", "..."],
  "risk_factors": ["<short phrase>", "..."],
  "news_context": ["<short phrase>", "..."],
  "trade_thesis": "<one or two sentences>"
}

Rules:
- Do not include any numeric price target, stop loss, quantity, or confidence
  score - those are already calculated deterministically and are not yours
  to set or restate as your own judgement.
- Do not claim guaranteed returns or predict a specific future price.
- If there is no notable news, return an empty news_context list.
""".strip()


def build_candidate_prompt(
    plan: TradePlan,
    indicators: Dict,
    news_headlines: List[str],
    market_regime: str,
) -> str:
    payload = {
        "symbol": plan.symbol,
        "market_regime": market_regime,
        "setup": plan.setup_type,
        "technical_score": plan.score,
        "price": plan.current_price,
        "entry_zone": [plan.entry_low, plan.entry_high],
        "stop_loss": plan.stop_loss,
        "target_1": plan.target_1,
        "target_2": plan.target_2,
        "risk_reward": plan.risk_reward,
        "indicators": indicators,
        "news": news_headlines,
    }
    return (
        "You are a technical-analysis assistant for an Indian equity "
        "swing-trading research tool. A deterministic strategy engine has "
        "already selected this setup and calculated every number below - "
        "your job is only to explain it in plain language, not to choose or "
        "adjust any trade parameter.\n\n"
        f"Structured input:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"{RESPONSE_SCHEMA_INSTRUCTIONS}"
    )
