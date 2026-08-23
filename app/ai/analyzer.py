import json
import logging
from typing import Dict, List

from pydantic import ValidationError

from app.ai.prompts import build_candidate_prompt
from app.ai.provider import LLMProvider, LLMProviderError
from app.schemas.ai import AIAnalysis, LLMExplanation
from app.strategy.strategy import TradePlan

logger = logging.getLogger(__name__)


def determine_confidence(
    plan: TradePlan,
    market_regime: str,
    has_negative_news: bool = False,
    data_quality_ok: bool = True,
) -> str:
    """Deterministic confidence label - the LLM never sets this (plan
    section 25: confidence must reflect evidence quality, not be an LLM
    probability estimate).
    """
    if not data_quality_ok or has_negative_news:
        return "LOW"
    if plan.score >= 85 and market_regime == "BULLISH":
        return "HIGH"
    if plan.score >= 75:
        return "MEDIUM"
    return "LOW"


def _parse_explanation(raw_text: str) -> LLMExplanation:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    data = json.loads(cleaned)
    return LLMExplanation(**data)


class CandidateAnalyzer:
    """Tries each configured provider in order; falls back to a
    deterministic-only result (ai_status="unavailable") if all of them fail
    or return unparseable output. The scanner must never break or block on
    this (plan section 45: LLM unavailable -> generate the report anyway).
    """

    def __init__(self, providers: List[LLMProvider]):
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers

    def analyze(
        self,
        plan: TradePlan,
        indicators: Dict,
        news_headlines: List[str],
        market_regime: str,
        has_negative_news: bool = False,
    ) -> AIAnalysis:
        confidence = determine_confidence(plan, market_regime, has_negative_news)
        prompt = build_candidate_prompt(plan, indicators, news_headlines, market_regime)

        for provider in self.providers:
            provider_name = type(provider).__name__
            try:
                raw = provider.complete(prompt)
                explanation = _parse_explanation(raw)
                return AIAnalysis(
                    explanation=explanation,
                    confidence=confidence,
                    ai_status="ok",
                    provider=provider_name,
                )
            except (LLMProviderError, json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"{provider_name} failed, trying next: {e}")
                continue

        logger.warning("All LLM providers failed; returning deterministic-only result")
        return AIAnalysis(
            explanation=None,
            confidence=confidence,
            ai_status="unavailable",
            provider=None,
        )
