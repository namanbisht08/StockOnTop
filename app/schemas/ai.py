from typing import List, Optional

from pydantic import BaseModel, Field

CONFIDENCE_LABELS = ("HIGH", "MEDIUM", "LOW")


class LLMExplanation(BaseModel):
    """Narrative-only structured output the LLM is asked to produce.

    Deliberately excludes any numeric trade parameter and the confidence
    label - those are computed deterministically (see analyzer.py) and are
    not the LLM's to set, per the plan's core design principle.
    """

    summary: str
    bullish_factors: List[str] = Field(default_factory=list)
    risk_factors: List[str] = Field(default_factory=list)
    news_context: List[str] = Field(default_factory=list)
    trade_thesis: str


class AIAnalysis(BaseModel):
    """Final AI context attached to a recommendation."""

    explanation: Optional[LLMExplanation]
    confidence: str  # one of CONFIDENCE_LABELS
    ai_status: str  # "ok" or "unavailable"
    provider: Optional[str] = None
