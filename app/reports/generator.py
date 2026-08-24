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

# HTML parse_mode - TelegramNotifier must be told to send with parse_mode="HTML"
# for this to render as a link rather than literal tag text.
BOT_FOOTER_HTML = (
    "Created by Naman Singh Bisht (namanbisht.com) · "
    '<a href="https://www.linkedin.com/in/naman-singh-bisht/">LinkedIn</a>'
)

DAILY_STATUS_LABELS = {
    "ENTERED": "Entry filled today",
    "STILL_WATCHING": "Waiting for entry",
    "EXPIRED_NO_FILL": "Expired - never entered the zone",
    "HOLD": "Holding",
    "STOPPED_OUT": "Stopped out today",
    "TARGET_1_HIT": "Target 1 hit today",
    "TIME_EXIT": "Time exit - holding period ended",
    "ERROR": "Status check failed",
}


def _regime_emoji(regime: str) -> str:
    return REGIME_EMOJI.get(regime, "⚪")


def _escape_html(text: str) -> str:
    """Telegram's HTML parse_mode only requires escaping these three - order
    matters (escape & first). Needed because some real NIFTY 500 tickers
    (M&M, GVT&D, ARE&M, J&KBANK) contain '&', which would otherwise break
    parsing of the footer's <a> tag and fail the entire send.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
    picks: List[TradePlan],
    market_regime: str,
    capital: float,
    note: Optional[str] = None,
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
        lines.append(_escape_html(note) if note else "NO TRADE THIS WEEK")
    else:
        if note:
            lines.append(_escape_html(note))
            lines.append("")
        for idx, plan in enumerate(picks):
            marker = PICK_EMOJI[idx] if idx < len(PICK_EMOJI) else f"{idx + 1}."
            symbol = _escape_html(plan.symbol)
            profit_t1 = (plan.target_1 - plan.entry_low) * plan.quantity
            profit_t2 = (plan.target_2 - plan.entry_low) * plan.quantity
            lines.extend(
                [
                    f"{marker} {symbol} - Score {plan.score:.0f}",
                    f"Entry: ₹{plan.entry_low:,.0f}-{plan.entry_high:,.0f}",
                    f"SL: ₹{plan.stop_loss:,.0f}",
                    f"T1: ₹{plan.target_1:,.0f}",
                    f"T2: ₹{plan.target_2:,.0f}",
                    f"R:R: {plan.risk_reward:.1f}",
                    f"Qty: {plan.quantity}",
                    f"Capital Required: ₹{plan.capital_required:,.0f}",
                    f"Risk (Max Loss): ₹{plan.max_loss:,.0f}",
                    f"Profit @T1: ₹{profit_t1:,.0f}",
                    f"Profit @T2: ₹{profit_t2:,.0f}",
                    "",
                ]
            )

    lines.append(BOT_FOOTER_HTML)
    return "\n".join(lines)


STILL_OPEN_STATUSES = ("ENTERED", "HOLD")


def _distance_line(entry: Dict) -> Optional[str]:
    """SL/T1/T2 distance from the current price, in both rupees and percent -
    only meaningful for a position that's still open (entered but not yet
    exited), using entry.get("current_price") as of today's close.
    """
    current_price = entry.get("current_price")
    stop_loss = entry.get("stop_loss")
    target_1 = entry.get("target_1")
    target_2 = entry.get("target_2")
    if current_price is None or stop_loss is None or target_1 is None or target_2 is None:
        return None
    if current_price <= 0:
        return None

    sl_rs = current_price - stop_loss
    sl_pct = sl_rs / current_price * 100
    t1_rs = target_1 - current_price
    t1_pct = t1_rs / current_price * 100
    t2_rs = target_2 - current_price
    t2_pct = t2_rs / current_price * 100

    return (
        f"   \U0001f6d1 SL: ₹{sl_rs:,.2f} ({sl_pct:+.1f}%) away  "
        f"\U0001f3af T1: ₹{t1_rs:,.2f} ({t1_pct:+.1f}%) away  "
        f"\U0001f3af T2: ₹{t2_rs:,.2f} ({t2_pct:+.1f}%) away"
    )


def generate_daily_status_message(digest: List[Dict]) -> str:
    """digest entries are dicts produced by app.jobs.daily_update - one per
    currently-open position. Beyond symbol/status/detail, an entry may carry
    entry_price/current_price/quantity/stop_loss/target_1/target_2 when
    priced data is available, used here for per-position SL/T1/T2 distance
    and the portfolio-level capital/standing summary.
    """
    lines = ["DAILY POSITION STATUS", ""]
    total_invested = 0.0
    total_standing = 0.0

    for entry in digest:
        label = DAILY_STATUS_LABELS.get(entry["status"], entry["status"])
        symbol = _escape_html(entry["symbol"])
        detail = _escape_html(entry["detail"])

        entry_price = entry.get("entry_price")
        current_price = entry.get("current_price")
        quantity = entry.get("quantity")
        priced = entry_price is not None and current_price is not None and quantity

        marker = ""
        if priced:
            marker = "\U0001f7e2 " if current_price >= entry_price else "\U0001f534 "
            total_invested += entry_price * quantity
            total_standing += current_price * quantity

        lines.append(f"{marker}{symbol}: {label} - {detail}")

        if entry["status"] in STILL_OPEN_STATUSES:
            distance_line = _distance_line(entry)
            if distance_line:
                lines.append(distance_line)

    if total_invested > 0:
        overall_pnl = total_standing - total_invested
        overall_pct = overall_pnl / total_invested * 100
        overall_marker = "\U0001f7e2" if overall_pnl >= 0 else "\U0001f534"
        lines.extend(
            [
                "",
                f"\U0001f4b0 Capital Invested: ₹{total_invested:,.0f}",
                f"\U0001f4ca Current Standing: ₹{total_standing:,.0f}",
                f"{overall_marker} Overall P&L: ₹{overall_pnl:,.0f} ({overall_pct:+.1f}%)",
            ]
        )

    lines.append("")
    lines.append(BOT_FOOTER_HTML)
    return "\n".join(lines)
