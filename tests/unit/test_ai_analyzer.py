from app.ai.analyzer import CandidateAnalyzer, determine_confidence
from app.ai.provider import MockLLMProvider
from app.strategy.strategy import TradePlan


def _plan(score: float = 80.0) -> TradePlan:
    return TradePlan(
        symbol="XYZ",
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


def test_determine_confidence_high_requires_bullish_and_strong_score():
    assert determine_confidence(_plan(90), "BULLISH") == "HIGH"
    assert determine_confidence(_plan(90), "NEUTRAL") == "MEDIUM"


def test_determine_confidence_medium_band():
    assert determine_confidence(_plan(78), "BULLISH") == "MEDIUM"


def test_determine_confidence_low_below_threshold():
    assert determine_confidence(_plan(60), "BULLISH") == "LOW"


def test_determine_confidence_low_on_negative_news_regardless_of_score():
    assert determine_confidence(_plan(95), "BULLISH", has_negative_news=True) == "LOW"


def test_determine_confidence_low_on_bad_data_quality():
    assert determine_confidence(_plan(95), "BULLISH", data_quality_ok=False) == "LOW"


def test_analyze_returns_ok_with_valid_provider_response():
    valid_json = (
        '{"summary": "Strong breakout", "bullish_factors": ["volume spike"], '
        '"risk_factors": ["sector volatility"], "news_context": [], '
        '"trade_thesis": "Momentum continuation play"}'
    )
    analyzer = CandidateAnalyzer([MockLLMProvider(response=valid_json)])

    result = analyzer.analyze(_plan(90), {}, [], "BULLISH")

    assert result.ai_status == "ok"
    assert result.provider == "MockLLMProvider"
    assert result.confidence == "HIGH"
    assert result.explanation.summary == "Strong breakout"
    assert result.explanation.bullish_factors == ["volume spike"]


def test_analyze_falls_back_to_next_provider_on_failure():
    valid_json = '{"summary": "ok", "trade_thesis": "thesis"}'
    failing = MockLLMProvider(fail=True)
    working = MockLLMProvider(response=valid_json)
    analyzer = CandidateAnalyzer([failing, working])

    result = analyzer.analyze(_plan(90), {}, [], "BULLISH")

    assert result.ai_status == "ok"
    assert result.provider == "MockLLMProvider"
    assert result.explanation.summary == "ok"


def test_analyze_returns_unavailable_when_all_providers_fail():
    analyzer = CandidateAnalyzer(
        [MockLLMProvider(fail=True), MockLLMProvider(fail=True)]
    )

    result = analyzer.analyze(_plan(90), {}, [], "BULLISH")

    assert result.ai_status == "unavailable"
    assert result.explanation is None
    assert result.provider is None
    # confidence must still be computed deterministically even without an LLM
    assert result.confidence == "HIGH"


def test_analyze_falls_back_when_provider_returns_invalid_json():
    analyzer = CandidateAnalyzer(
        [
            MockLLMProvider(response="not json"),
            MockLLMProvider(response="also not json"),
        ]
    )

    result = analyzer.analyze(_plan(90), {}, [], "BULLISH")

    assert result.ai_status == "unavailable"


def test_analyze_falls_back_when_provider_omits_required_field():
    # missing required "trade_thesis" field
    analyzer = CandidateAnalyzer([MockLLMProvider(response='{"summary": "ok"}')])

    result = analyzer.analyze(_plan(90), {}, [], "BULLISH")

    assert result.ai_status == "unavailable"


def test_analyze_strips_markdown_json_fence():
    fenced = '```json\n{"summary": "ok", "trade_thesis": "thesis"}\n```'
    analyzer = CandidateAnalyzer([MockLLMProvider(response=fenced)])

    result = analyzer.analyze(_plan(90), {}, [], "BULLISH")

    assert result.ai_status == "ok"
    assert result.explanation.summary == "ok"
