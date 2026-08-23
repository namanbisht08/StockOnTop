from datetime import date
from typing import Dict, List, Optional

from app.schemas.ai import AIAnalysis
from app.strategy.strategy import TradePlan

REGIME_EMOJI = {
    "BULLISH": "\U0001f7e2",
    "NEUTRAL": "\U0001f7e1",
    "BEARISH": "\U0001f534",
}
PICK_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

DISCLAIMER = "Educational/research output. No guaranteed returns."


def _regime_emoji(regime: str) -> str:
    return REGIME_EMOJI.get(regime, "⚪")


def generate_text_report(
    picks: List[TradePlan],
    market_regime: str,
    capital: float,
    report_date: date,
    ai_analyses: Optional[Dict[str, AIAnalysis]] = None,
) -> str:
    """The detailed report (plan section 27) - always deterministic; AI
    context is appended per pick only when available, never required.
    """
    ai_analyses = ai_analyses or {}
    lines = [
        "=" * 50,
        "AI SWING TRADING - WEEKLY REPORT",
        f"Date: {report_date.isoformat()}",
        f"Capital: ₹{capital:,.0f}",
        f"Market Regime: {market_regime}",
        "=" * 50,
        "",
    ]

    if not picks:
        lines.append("NO TRADE THIS WEEK")
        lines.append("")
        lines.append("No candidate met the configured strategy thresholds this week.")
        return "\n".join(lines)

    lines.append("TOP PICKS")
    lines.append("")
    for idx, plan in enumerate(picks):
        lines.extend(
            [
                f"#{idx + 1} {plan.symbol}",
                f"Score: {plan.score:.0f}/100",
                f"Setup: {plan.setup_type}",
                "",
                f"CMP: ₹{plan.current_price:,.2f}",
                f"Entry: ₹{plan.entry_low:,.2f}-₹{plan.entry_high:,.2f}",
                f"Stop: ₹{plan.stop_loss:,.2f}",
                f"Target 1: ₹{plan.target_1:,.2f}",
                f"Target 2: ₹{plan.target_2:,.2f}",
                "",
                f"Risk/Reward: {plan.risk_reward:.1f}",
                f"Quantity: {plan.quantity}",
                f"Capital: ₹{plan.capital_required:,.2f}",
                f"Maximum Loss: ₹{plan.max_loss:,.2f}",
            ]
        )

        analysis = ai_analyses.get(plan.symbol)
        lines.append(f"Confidence: {analysis.confidence if analysis else 'N/A'}")
        if analysis and analysis.explanation:
            lines.append("")
            lines.append(f"Why: {analysis.explanation.trade_thesis}")
            for factor in analysis.explanation.bullish_factors:
                lines.append(f"- {factor}")
            if analysis.explanation.risk_factors:
                lines.append("Risks:")
                for factor in analysis.explanation.risk_factors:
                    lines.append(f"- {factor}")

        lines.append("")
        lines.append("-" * 50)
        lines.append("")

    lines.append(DISCLAIMER)
    return "\n".join(lines)


def generate_telegram_message(
    picks: List[TradePlan], market_regime: str, capital: float
) -> str:
    """The compact notification (plan section 28)."""
    lines = [
        "WEEKLY SWING WATCHLIST",
        "",
        f"Market: {_regime_emoji(market_regime)} {market_regime}",
        f"Capital: ₹{capital:,.0f}",
        "",
    ]

    if not picks:
        lines.append("NO TRADE THIS WEEK")
    else:
        for idx, plan in enumerate(picks):
            marker = PICK_EMOJI[idx] if idx < len(PICK_EMOJI) else f"{idx + 1}."
            lines.extend(
                [
                    f"{marker} {plan.symbol} - Score {plan.score:.0f}",
                    f"Entry: ₹{plan.entry_low:,.0f}-{plan.entry_high:,.0f}",
                    f"SL: ₹{plan.stop_loss:,.0f}",
                    f"T1: ₹{plan.target_1:,.0f}",
                    f"T2: ₹{plan.target_2:,.0f}",
                    f"R:R: {plan.risk_reward:.1f}",
                    f"Qty: {plan.quantity}",
                    f"Risk: ₹{plan.max_loss:,.0f}",
                    "",
                ]
            )

    lines.append(DISCLAIMER)
    return "\n".join(lines)
