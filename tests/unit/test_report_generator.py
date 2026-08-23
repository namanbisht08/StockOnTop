from datetime import date

from app.reports.generator import (
    generate_daily_status_message,
    generate_telegram_message,
    generate_text_report,
)
from app.schemas.ai import AIAnalysis, LLMExplanation
from app.strategy.strategy import TradePlan


def _plan(symbol="XYZ", score=87.0) -> TradePlan:
    return TradePlan(
        symbol=symbol,
        setup_type="BREAKOUT",
        score=score,
        current_price=1250.0,
        entry_low=1250.0,
        entry_high=1265.0,
        stop_loss=1210.0,
        target_1=1350.0,
        target_2=1420.0,
        risk_reward=2.4,
        quantity=24,
        capital_required=30_240.0,
        max_loss=1_080.0,
    )


def test_text_report_no_trade_this_week():
    report = generate_text_report([], "BEARISH", 100_000.0, date(2024, 1, 1))
    assert "NO TRADE THIS WEEK" in report
    assert "BEARISH" in report


def test_text_report_includes_pick_details():
    report = generate_text_report([_plan()], "BULLISH", 100_000.0, date(2024, 1, 1))

    assert "#1 XYZ" in report
    assert "Score: 87/100" in report
    assert "Entry: ₹1,250.00-₹1,265.00" in report
    assert "Stop: ₹1,210.00" in report
    assert "Risk/Reward: 2.4" in report
    assert "Quantity: 24" in report
    assert "Confidence: N/A" in report


def test_text_report_includes_ai_explanation_when_available():
    analysis = AIAnalysis(
        explanation=LLMExplanation(
            summary="Strong breakout",
            bullish_factors=["volume spike"],
            risk_factors=["sector volatility"],
            news_context=[],
            trade_thesis="Momentum continuation play",
        ),
        confidence="HIGH",
        ai_status="ok",
        provider="MockLLMProvider",
    )
    report = generate_text_report(
        [_plan()],
        "BULLISH",
        100_000.0,
        date(2024, 1, 1),
        ai_analyses={"XYZ": analysis},
    )

    assert "Confidence: HIGH" in report
    assert "Momentum continuation play" in report
    assert "volume spike" in report
    assert "sector volatility" in report


def test_telegram_message_no_trade_this_week():
    message = generate_telegram_message([], "BEARISH", 100_000.0)
    assert "NO TRADE THIS WEEK" in message


def test_telegram_message_includes_pick_and_disclaimer():
    message = generate_telegram_message([_plan()], "BULLISH", 100_000.0)

    assert "1️⃣ XYZ - Score 87" in message
    assert "Entry: ₹1,250-1,265" in message
    assert "SL: ₹1,210" in message
    assert "Qty: 24" in message
    assert "No guaranteed returns." in message


def test_telegram_message_numbers_multiple_picks():
    message = generate_telegram_message(
        [_plan("AAA", 90), _plan("BBB", 80)], "BULLISH", 100_000.0
    )
    assert "1️⃣ AAA" in message
    assert "2️⃣ BBB" in message


def test_telegram_message_note_replaces_no_trade_line_when_no_picks():
    message = generate_telegram_message(
        [], "NEUTRAL", 100_000.0, note="All 4 tracked positions are already open."
    )
    assert "All 4 tracked positions are already open." in message
    assert "NO TRADE THIS WEEK" not in message


def test_telegram_message_note_is_shown_alongside_picks():
    message = generate_telegram_message(
        [_plan()], "BULLISH", 100_000.0, note="1 slot was already filled this week."
    )
    assert "1 slot was already filled this week." in message
    assert "1️⃣ XYZ" in message


def test_daily_status_message_formats_each_entry():
    digest = [
        {"symbol": "XYZ", "status": "HOLD", "detail": "day 2 of 20"},
        {
            "symbol": "ABC",
            "status": "STOPPED_OUT",
            "detail": "exit at Rs.95.00, net P&L Rs.-500.00",
        },
    ]
    message = generate_daily_status_message(digest)

    assert "XYZ: Holding - day 2 of 20" in message
    assert "ABC: Stopped out today - exit at Rs.95.00, net P&L Rs.-500.00" in message
    assert "No guaranteed returns." in message


def test_daily_status_message_falls_back_to_raw_status_for_unknown_codes():
    digest = [{"symbol": "XYZ", "status": "SOMETHING_NEW", "detail": "n/a"}]
    message = generate_daily_status_message(digest)
    assert "XYZ: SOMETHING_NEW - n/a" in message
