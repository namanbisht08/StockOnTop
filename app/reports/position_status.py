"""Builds the enhanced DAILY POSITION STATUS message: per-position P&L and
distance-to-SL/T1/T2, plus a portfolio-level summary.

All money/percentage arithmetic here uses Decimal - the digest dicts coming
out of app.jobs.daily_update carry floats (as stored on the ORM models), so
values are converted once at the boundary (_to_decimal) and never touched as
floats again. Realized P&L is not recomputed from scratch: it reuses the
net_pnl already computed by app.jobs.daily_update._apply_exit (which already
accounts for brokerage/STT/etc. via calculate_charges), so this module never
duplicates or drifts from the existing trading-cost logic.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)

STATUS_LABELS = {
    "ENTERED": "Entry filled today",
    "STILL_WATCHING": "Waiting for entry",
    "EXPIRED_NO_FILL": "Expired - never entered the zone",
    "HOLD": "Active",
    "STOPPED_OUT": "Stopped out today",
    "TARGET_1_HIT": "Target 1 achieved",
    "TARGET_2_HIT": "Target 2 achieved",
    "TIME_EXIT": "Exited",
    "ERROR": "Status check failed",
}

# Positions where an entry has filled and P&L applies.
OPEN_PRICED_STATUSES = ("ENTERED", "HOLD")
CLOSED_PRICED_STATUSES = ("STOPPED_OUT", "TARGET_1_HIT", "TARGET_2_HIT", "TIME_EXIT")

# Cosmetic only - purely additive prefixes/wrapping, never change the
# underlying wording, so they can't affect any calculation above.
CLOSED_STATUS_EMOJI = {
    "ENTERED": "🆕",
    "STOPPED_OUT": "🔴",
    "TARGET_1_HIT": "🏆",
    "TARGET_2_HIT": "🏆",
    "TIME_EXIT": "⏱️",
}
SIMPLE_STATUS_EMOJI = {
    "STILL_WATCHING": "⏳",
    "EXPIRED_NO_FILL": "❌",
    "ERROR": "⚠️",
}


def _pnl_emoji(value: Optional[Decimal]) -> str:
    if value is None:
        return "⚪"
    return "🟢" if value >= 0 else "🔴"

BOT_FOOTER_HTML = (
    "Created by Naman Singh Bisht (namanbisht.com) · "
    '<a href="https://www.linkedin.com/in/naman-singh-bisht/">LinkedIn</a>'
)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _to_decimal(value) -> Optional[Decimal]:
    """None-safe float/int -> Decimal, going via str() so the result is the
    decimal a human would read off the float rather than its raw binary
    representation (Decimal(0.1) != Decimal("0.1")).
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


@dataclass
class PositionReport:
    symbol: str
    status: str
    detail: str
    quantity: Optional[int] = None
    # Present only when the recommended size differs from what was actually
    # executed - this system doesn't currently model partial fills, so it's
    # None in production; supported here so the reporting layer doesn't have
    # to change if that tracking is added later.
    executed_quantity: Optional[int] = None
    entry_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    target_1: Optional[Decimal] = None
    target_2: Optional[Decimal] = None
    current_price: Optional[Decimal] = None  # today's close, open positions only
    exit_price: Optional[Decimal] = None  # actual fill price, closed positions only
    realized_pnl: Optional[Decimal] = None  # net of charges, from the trading layer

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_PRICED_STATUSES

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_PRICED_STATUSES

    @property
    def effective_quantity(self) -> Optional[int]:
        return self.executed_quantity if self.executed_quantity is not None else self.quantity


@dataclass
class PortfolioSummary:
    cumulative_invested: Decimal
    active_invested: Decimal
    active_current_value: Decimal
    total_realized_pnl: Decimal
    total_unrealized_pnl: Decimal
    overall_pnl: Decimal
    overall_pnl_pct: Optional[Decimal]
    overall_portfolio_value: Decimal
    missing_close_symbols: List[str]


def format_inr(value: Optional[Decimal]) -> str:
    """₹ with Indian (lakh/crore) digit grouping, e.g. Decimal('1234567.5')
    -> '₹12,34,567.50'. Unsigned - callers pass already-nonnegative amounts.
    """
    if value is None:
        return "N/A"
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if quantized < 0 else ""
    int_part, _, dec_part = f"{abs(quantized):.2f}".partition(".")
    return f"{sign}₹{_group_indian(int_part)}.{dec_part}"


def format_signed_inr(value: Optional[Decimal]) -> str:
    """Like format_inr, but always shows a leading +/- - for P&L figures."""
    if value is None:
        return "N/A"
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "+" if quantized >= 0 else "-"
    int_part, _, dec_part = f"{abs(quantized):.2f}".partition(".")
    return f"{sign}₹{_group_indian(int_part)}.{dec_part}"


def format_pct(value: Optional[Decimal]) -> str:
    if value is None:
        return "N/A"
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "+" if quantized >= 0 else "-"
    return f"{sign}{abs(quantized):.2f}%"


def _group_indian(int_part: str) -> str:
    if len(int_part) <= 3:
        return int_part
    last3 = int_part[-3:]
    remaining = int_part[:-3]
    groups: List[str] = []
    while len(remaining) > 2:
        groups.insert(0, remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        groups.insert(0, remaining)
    return ",".join(groups + [last3])


def invested_amount(quantity: Optional[int], entry_price: Optional[Decimal]) -> Optional[Decimal]:
    if not quantity or entry_price is None:
        return None
    return Decimal(quantity) * entry_price


def price_distance_pct(
    entry_price: Optional[Decimal], level_price: Optional[Decimal]
) -> Optional[Decimal]:
    """(level - entry) / entry * 100 - negative for a level below entry (SL),
    positive for a level above entry (T1/T2). Same formula for all three;
    the sign is what distinguishes downside from upside.
    """
    if entry_price is None or level_price is None or entry_price == 0:
        return None
    return (level_price - entry_price) / entry_price * Decimal(100)


def current_market_value(
    quantity: Optional[int], current_price: Optional[Decimal]
) -> Optional[Decimal]:
    if not quantity or current_price is None:
        return None
    return Decimal(quantity) * current_price


def unrealized_pnl(
    entry_price: Optional[Decimal], current_price: Optional[Decimal], quantity: Optional[int]
) -> Optional[Tuple[Decimal, Decimal]]:
    invested = invested_amount(quantity, entry_price)
    if (
        invested is None
        or invested == 0
        or current_price is None
        or entry_price is None
        or quantity is None
    ):
        return None
    pnl = (current_price - entry_price) * Decimal(quantity)
    return pnl, pnl / invested * Decimal(100)


def realized_pnl_pct(
    realized_pnl_value: Optional[Decimal], invested: Optional[Decimal]
) -> Optional[Decimal]:
    if realized_pnl_value is None or invested is None or invested == 0:
        return None
    return realized_pnl_value / invested * Decimal(100)


def build_position_report(entry: Dict) -> PositionReport:
    """Converts one digest dict (as produced by app.jobs.daily_update) into
    a PositionReport, doing the float->Decimal boundary conversion once.
    """
    status = entry["status"]
    quantity = entry.get("quantity") or None

    report = PositionReport(
        symbol=entry["symbol"],
        status=status,
        detail=entry.get("detail", ""),
        quantity=quantity,
        entry_price=_to_decimal(entry.get("entry_price")),
        stop_loss=_to_decimal(entry.get("stop_loss")),
        target_1=_to_decimal(entry.get("target_1")),
        target_2=_to_decimal(entry.get("target_2")),
    )

    if status in CLOSED_PRICED_STATUSES:
        report.exit_price = _to_decimal(entry.get("current_price"))
        report.realized_pnl = _to_decimal(entry.get("net_pnl"))
    elif status in OPEN_PRICED_STATUSES:
        report.current_price = _to_decimal(entry.get("current_price"))

    return report


def build_portfolio_summary(reports: List[PositionReport]) -> PortfolioSummary:
    cumulative_invested = Decimal(0)
    active_invested = Decimal(0)
    active_current_value = Decimal(0)
    total_realized_pnl = Decimal(0)
    total_unrealized_pnl = Decimal(0)
    missing_close_symbols: List[str] = []

    for report in reports:
        qty = report.effective_quantity
        invested = invested_amount(qty, report.entry_price)
        if invested is None:
            continue
        cumulative_invested += invested

        if report.is_closed:
            if report.realized_pnl is not None:
                total_realized_pnl += report.realized_pnl
        elif report.is_open:
            active_invested += invested
            if report.current_price is None:
                missing_close_symbols.append(report.symbol)
                continue
            market_value = current_market_value(qty, report.current_price)
            if market_value is not None:
                active_current_value += market_value
            pnl = unrealized_pnl(report.entry_price, report.current_price, qty)
            if pnl is not None:
                total_unrealized_pnl += pnl[0]

    if missing_close_symbols:
        logger.warning(
            "Missing today's closing price for: %s - excluded from unrealized P&L",
            ", ".join(missing_close_symbols),
        )

    overall_pnl = total_realized_pnl + total_unrealized_pnl
    overall_pnl_pct = (
        overall_pnl / cumulative_invested * Decimal(100) if cumulative_invested else None
    )
    overall_portfolio_value = cumulative_invested + overall_pnl

    return PortfolioSummary(
        cumulative_invested=cumulative_invested,
        active_invested=active_invested,
        active_current_value=active_current_value,
        total_realized_pnl=total_realized_pnl,
        total_unrealized_pnl=total_unrealized_pnl,
        overall_pnl=overall_pnl,
        overall_pnl_pct=overall_pnl_pct,
        overall_portfolio_value=overall_portfolio_value,
        missing_close_symbols=missing_close_symbols,
    )


def _quantity_line(report: PositionReport) -> str:
    if report.quantity is None:
        return "Qty: N/A"
    if report.executed_quantity is not None and report.executed_quantity != report.quantity:
        return f"Qty: {report.executed_quantity} (recommended {report.quantity})"
    return f"Qty: {report.quantity}"


def _sl_t1_t2_lines(report: PositionReport) -> List[str]:
    lines = []
    sl_pct = price_distance_pct(report.entry_price, report.stop_loss)
    if report.stop_loss is not None and sl_pct is not None:
        lines.append(
            f"🛑 SL: {format_inr(report.stop_loss)} ({format_pct(sl_pct)} from entry)"
        )
    else:
        lines.append("🛑 SL: N/A")

    for label, emoji, level in (
        ("T1", "🎯", report.target_1),
        ("T2", "🚀", report.target_2),
    ):
        pct = price_distance_pct(report.entry_price, level)
        if level is not None and pct is not None:
            lines.append(f"{emoji} {label}: {format_inr(level)} ({format_pct(pct)})")
        else:
            lines.append(f"{emoji} {label}: N/A")
    return lines


def _render_priced_block(report: PositionReport) -> List[str]:
    symbol = _escape_html(report.symbol)
    label = STATUS_LABELS.get(report.status, report.status).upper()

    qty = report.effective_quantity
    invested = invested_amount(qty, report.entry_price)
    unrealized = None
    if report.is_open and report.current_price is not None:
        unrealized = unrealized_pnl(report.entry_price, report.current_price, qty)

    if report.is_open:
        header_emoji = _pnl_emoji(unrealized[0]) if unrealized else "🔷"
    else:
        header_emoji = CLOSED_STATUS_EMOJI.get(report.status, "⚪")

    lines = [
        f"{header_emoji} <b>{symbol} — {label}</b>",
        f"📦 {_quantity_line(report)}",
        f"📍 Entry: {format_inr(report.entry_price)}",
        f"💵 Invested: {format_inr(invested)}",
    ]

    if report.is_open:
        if report.current_price is not None:
            lines.append(f"🔔 Close: {format_inr(report.current_price)}")
            lines.append(
                f"📈 Current value: {format_inr(current_market_value(qty, report.current_price))}"
            )
        else:
            lines.append("🔕 Close: N/A (no new data yet)")
            lines.append("📈 Current value: N/A")

    lines.extend(_sl_t1_t2_lines(report))

    if report.is_closed:
        lines.append(f"🏁 Exit: {format_inr(report.exit_price)}")
        pct = realized_pnl_pct(report.realized_pnl, invested)
        if report.realized_pnl is not None:
            lines.append(
                f"{_pnl_emoji(report.realized_pnl)} <b>Realized P&L: "
                f"{format_signed_inr(report.realized_pnl)} ({format_pct(pct)})</b>"
            )
        else:
            lines.append("⚪ Realized P&L: N/A")
    elif report.is_open:
        if report.current_price is not None and unrealized is not None:
            lines.append(
                f"{_pnl_emoji(unrealized[0])} <b>Unrealized P&L: "
                f"{format_signed_inr(unrealized[0])} ({format_pct(unrealized[1])})</b>"
            )
        elif report.current_price is not None:
            lines.append("⚪ Unrealized P&L: N/A")
        else:
            lines.append("⚪ Unrealized P&L: N/A (no new data yet)")

    return lines


def _render_simple_block(entry: Dict) -> List[str]:
    """STILL_WATCHING / EXPIRED_NO_FILL / ERROR - no capital deployed yet
    (or the check itself failed), so there's nothing to price.
    """
    label = STATUS_LABELS.get(entry["status"], entry["status"])
    symbol = _escape_html(entry["symbol"])
    detail = _escape_html(entry.get("detail", ""))
    emoji = SIMPLE_STATUS_EMOJI.get(entry["status"], "❔")
    return [f"{emoji} {symbol}: {label} - {detail}"]


def _portfolio_summary_lines(summary: PortfolioSummary) -> List[str]:
    mood = "🎉" if summary.overall_pnl >= 0 else "😬"
    return [
        "",
        "💼 <b>PORTFOLIO SUMMARY</b>",
        f"💰 Cumulative invested: {format_inr(summary.cumulative_invested)}",
        f"🏦 Active capital invested: {format_inr(summary.active_invested)}",
        f"📊 Active positions value: {format_inr(summary.active_current_value)}",
        f"{_pnl_emoji(summary.total_realized_pnl)} Realized P&L: "
        f"{format_signed_inr(summary.total_realized_pnl)}",
        f"{_pnl_emoji(summary.total_unrealized_pnl)} Unrealized P&L: "
        f"{format_signed_inr(summary.total_unrealized_pnl)}",
        f"{_pnl_emoji(summary.overall_pnl)} <b>Overall P&L: "
        f"{format_signed_inr(summary.overall_pnl)} ({format_pct(summary.overall_pnl_pct)})</b> {mood}",
        f"🏆 Overall portfolio value: {format_inr(summary.overall_portfolio_value)}",
    ]


def render_daily_status_message(digest: List[Dict]) -> str:
    lines = [
        "📊 <b>DAILY POSITION STATUS</b>",
        f"🗓️ {date.today().strftime('%d %b %Y')}",
        "",
    ]
    priced_reports: List[PositionReport] = []

    for entry in digest:
        status = entry["status"]
        if status in OPEN_PRICED_STATUSES or status in CLOSED_PRICED_STATUSES:
            report = build_position_report(entry)
            priced_reports.append(report)
            lines.extend(_render_priced_block(report))
        else:
            lines.extend(_render_simple_block(entry))
        lines.append("")

    if priced_reports:
        summary = build_portfolio_summary(priced_reports)
        if summary.cumulative_invested > 0:
            lines.extend(_portfolio_summary_lines(summary))
            lines.append("")

    lines.append(BOT_FOOTER_HTML)
    return "\n".join(lines)
