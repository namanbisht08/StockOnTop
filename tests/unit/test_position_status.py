from decimal import Decimal

from app.reports.position_status import (
    build_portfolio_summary,
    build_position_report,
    current_market_value,
    format_inr,
    format_pct,
    format_signed_inr,
    invested_amount,
    price_distance_pct,
    render_daily_status_message,
    unrealized_pnl,
)


def _priced_entry(**overrides):
    entry = {
        "symbol": "XYZ",
        "status": "HOLD",
        "detail": "day 2 of 20",
        "entry_price": 100.0,
        "current_price": 120.0,
        "quantity": 10,
        "stop_loss": 90.0,
        "target_1": 130.0,
        "target_2": 150.0,
    }
    entry.update(overrides)
    return entry


# --- formatting -------------------------------------------------------


def test_format_inr_uses_indian_lakh_grouping():
    assert format_inr(Decimal("1234567.5")) == "₹12,34,567.50"
    assert format_inr(Decimal("999.5")) == "₹999.50"
    assert format_inr(Decimal("100000")) == "₹1,00,000.00"
    assert format_inr(None) == "N/A"


def test_format_signed_inr_always_shows_sign():
    assert format_signed_inr(Decimal("111.1")) == "+₹111.10"
    assert format_signed_inr(Decimal("-1091.362")) == "-₹1,091.36"
    assert format_signed_inr(Decimal("0")) == "+₹0.00"


def test_format_pct_always_shows_sign():
    assert format_pct(Decimal("18.2")) == "+18.20%"
    assert format_pct(Decimal("-4.594")) == "-4.59%"


# --- pure calculation functions ----------------------------------------


def test_price_distance_pct_negative_for_stop_positive_for_targets():
    entry = Decimal("100")
    assert price_distance_pct(entry, Decimal("90")) == Decimal("-10")
    assert price_distance_pct(entry, Decimal("130")) == Decimal("30")


def test_price_distance_pct_guards_zero_entry():
    assert price_distance_pct(Decimal("0"), Decimal("90")) is None
    assert price_distance_pct(None, Decimal("90")) is None
    assert price_distance_pct(Decimal("100"), None) is None


def test_invested_amount_guards_zero_and_missing():
    assert invested_amount(10, Decimal("100")) == Decimal("1000")
    assert invested_amount(0, Decimal("100")) is None
    assert invested_amount(None, Decimal("100")) is None
    assert invested_amount(10, None) is None


def test_unrealized_pnl_profitable_and_loss_making():
    profit = unrealized_pnl(Decimal("100"), Decimal("120"), 10)
    assert profit == (Decimal("200"), Decimal("20"))

    loss = unrealized_pnl(Decimal("100"), Decimal("92"), 10)
    assert loss == (Decimal("-80"), Decimal("-8"))


def test_unrealized_pnl_none_when_current_price_missing():
    assert unrealized_pnl(Decimal("100"), None, 10) is None


def test_current_market_value_guards_zero_quantity():
    assert current_market_value(10, Decimal("50")) == Decimal("500")
    assert current_market_value(0, Decimal("50")) is None


# --- build_position_report / rendering ----------------------------------


def test_active_profitable_position_renders_correctly():
    message = render_daily_status_message([_priced_entry()])

    assert "XYZ — ACTIVE" in message
    assert "Qty: 10" in message
    assert "Entry: ₹100.00" in message
    assert "Invested: ₹1,000.00" in message
    assert "Close: ₹120.00" in message
    assert "Current value: ₹1,200.00" in message
    assert "SL: ₹90.00 (-10.00% from entry)" in message
    assert "T1: ₹130.00 (+30.00%)" in message
    assert "T2: ₹150.00 (+50.00%)" in message
    assert "Unrealized P&L: +₹200.00 (+20.00%)" in message


def test_active_loss_making_position_renders_negative_pnl():
    message = render_daily_status_message(
        [_priced_entry(current_price=92.0)]
    )
    assert "Unrealized P&L: -₹80.00 (-8.00%)" in message


def test_stopped_out_position_uses_realized_pnl_not_close_price():
    entry = _priced_entry(
        status="STOPPED_OUT",
        detail="exit at Rs.90.00, net P&L Rs.-120.50",
        current_price=90.0,  # this is the exit price for a closed position
        net_pnl=-120.5,
    )
    message = render_daily_status_message([entry])

    assert "XYZ — STOPPED OUT TODAY" in message
    assert "Exit: ₹90.00" in message
    assert "Realized P&L: -₹120.50 (-12.05%)" in message
    # this position's own block must not show a Close/Current value/Unrealized
    # line (those only apply to still-open positions) - the aggregate
    # "Unrealized P&L" in PORTFOLIO SUMMARY is a separate, portfolio-wide line.
    position_block = message.split("PORTFOLIO SUMMARY")[0]
    assert "Unrealized P&L" not in position_block
    assert "Current value" not in position_block


def test_target_1_achieved_position():
    entry = _priced_entry(
        status="TARGET_1_HIT",
        detail="exit at Rs.130.00, net P&L Rs.280.00",
        current_price=130.0,
        net_pnl=280.0,
    )
    message = render_daily_status_message([entry])

    assert "XYZ — TARGET 1 ACHIEVED" in message
    assert "Realized P&L: +₹280.00 (+28.00%)" in message


def test_multiple_positions_mixed_statuses_portfolio_summary():
    active = _priced_entry(symbol="AAA", current_price=120.0)  # +200 unrealized
    stopped = _priced_entry(
        symbol="BBB",
        status="STOPPED_OUT",
        detail="exit at Rs.90.00, net P&L Rs.-120.50",
        current_price=90.0,
        net_pnl=-120.5,
    )
    watching = {"symbol": "CCC", "status": "STILL_WATCHING", "detail": "day 1 of 5"}

    message = render_daily_status_message([active, stopped, watching])

    assert "CCC: Waiting for entry - day 1 of 5" in message
    assert "PORTFOLIO SUMMARY" in message
    # cumulative invested = 1000 (AAA) + 1000 (BBB) = 2000
    assert "Cumulative invested: ₹2,000.00" in message
    # only AAA is still open
    assert "Active capital invested: ₹1,000.00" in message
    assert "Active positions value: ₹1,200.00" in message
    assert "Realized P&L: -₹120.50" in message
    assert "Unrealized P&L: +₹200.00" in message
    # overall = -120.50 + 200.00 = 79.50, pct = 79.50/2000*100 = 3.975 -> 3.98
    assert "Overall P&L: +₹79.50 (+3.98%)" in message
    # overall portfolio value = 2000 + 79.50 = 2079.50
    assert "Overall portfolio value: ₹2,079.50" in message


def test_missing_closing_price_excluded_from_unrealized_and_active_value():
    entry = _priced_entry(current_price=None)
    message = render_daily_status_message([entry])

    assert "Close: N/A (no new data yet)" in message
    assert "Current value: N/A" in message
    assert "Unrealized P&L: N/A" in message
    # capital committed still counts (entry_price/quantity are known), but
    # nothing was marked to market since today's close is missing
    assert "PORTFOLIO SUMMARY" in message
    assert "Active positions value: ₹0.00" in message
    assert "Unrealized P&L: +₹0.00" in message


def test_missing_closing_price_logs_a_warning_naming_the_symbol(caplog):
    import logging

    report = build_position_report(_priced_entry(symbol="URBANCO", current_price=None))
    with caplog.at_level(logging.WARNING, logger="app.reports.position_status"):
        build_portfolio_summary([report])
    assert any("URBANCO" in record.message for record in caplog.records)


def test_missing_sl_or_targets_render_as_na_without_crashing():
    entry = _priced_entry(stop_loss=None, target_1=None, target_2=None)
    message = render_daily_status_message([entry])

    assert "SL: N/A" in message
    assert "T1: N/A" in message
    assert "T2: N/A" in message
    # the rest of the position still renders fine
    assert "Unrealized P&L: +₹200.00 (+20.00%)" in message


def test_zero_quantity_position_shows_na_and_no_division_by_zero():
    entry = _priced_entry(quantity=0)
    message = render_daily_status_message([entry])

    assert "Invested: N/A" in message
    assert "Current value: N/A" in message
    assert "Unrealized P&L: N/A" in message
    assert "PORTFOLIO SUMMARY" not in message


def test_partially_filled_position_shows_both_quantities():
    report = build_position_report(_priced_entry())
    report.executed_quantity = 6  # only 6 of the recommended 10 actually filled

    assert report.effective_quantity == 6
    summary = build_portfolio_summary([report])
    # invested/current value must use the *executed* quantity, not recommended
    assert summary.active_invested == Decimal("600")  # 6 * 100
    assert summary.active_current_value == Decimal("720")  # 6 * 120


def test_fully_filled_position_quantity_line_shows_single_value():
    report = build_position_report(_priced_entry())
    assert report.executed_quantity is None
    assert report.effective_quantity == 10


def test_position_never_filled_is_excluded_from_portfolio_entirely():
    watching = {"symbol": "CCC", "status": "STILL_WATCHING", "detail": "day 1 of 5"}
    expired = {
        "symbol": "DDD",
        "status": "EXPIRED_NO_FILL",
        "detail": "never entered the zone within 5 days",
    }
    message = render_daily_status_message([watching, expired])

    assert "CCC: Waiting for entry - day 1 of 5" in message
    assert "DDD: Expired - never entered the zone - never entered the zone within 5 days" in message
    assert "PORTFOLIO SUMMARY" not in message


def test_portfolio_summary_calculation_directly():
    reports = [
        build_position_report(_priced_entry(symbol="AAA")),  # active, +200 unrealized
        build_position_report(
            _priced_entry(
                symbol="BBB",
                status="STOPPED_OUT",
                current_price=90.0,
                net_pnl=-120.5,
            )
        ),
    ]
    summary = build_portfolio_summary(reports)

    assert summary.cumulative_invested == Decimal("2000")
    assert summary.active_invested == Decimal("1000")
    assert summary.active_current_value == Decimal("1200")
    assert summary.total_realized_pnl == Decimal("-120.5")
    assert summary.total_unrealized_pnl == Decimal("200")
    assert summary.overall_pnl == Decimal("79.5")
    assert summary.overall_pnl_pct == Decimal("3.975")
    assert summary.overall_portfolio_value == Decimal("2079.5")
    assert summary.missing_close_symbols == []


def test_footer_and_no_disclaimer_preserved():
    message = render_daily_status_message([_priced_entry()])
    assert (
        '<a href="https://www.linkedin.com/in/naman-singh-bisht/">LinkedIn</a>'
        in message
    )
    assert "Naman Singh Bisht" in message
    assert "No guaranteed returns." not in message
