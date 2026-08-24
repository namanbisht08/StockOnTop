from datetime import date, timedelta

import httpx
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.jobs.daily_update as daily_update_module
from app.db.models import (
    Base,
    DailyUpdateRun,
    Recommendation,
    RecommendationOutcome,
    ScanRun,
    Stock,
)


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("unexpected real HTTP call in a daily_update test")

    monkeypatch.setattr(httpx, "post", _fail)


class _FakeProvider:
    """Deterministic in-memory OHLCV source, keyed by symbol."""

    def __init__(self, candles_by_symbol):
        self.candles_by_symbol = candles_by_symbol

    def get_ohlcv(self, symbol, start, end):
        # Mirrors real yfinance: `end` is exclusive.
        df = self.candles_by_symbol.get(symbol, pd.DataFrame())
        if df.empty:
            return df
        mask = (df["timestamp"] >= start) & (df["timestamp"] < end)
        return df[mask].reset_index(drop=True)


def _candles(rows):
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])


@pytest.fixture
def test_session(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    test_session_local = sessionmaker(bind=engine)
    monkeypatch.setattr(daily_update_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(
        daily_update_module,
        "get_settings",
        lambda: type("S", (), {"telegram_bot_token": None, "telegram_chat_id": None})(),
    )
    return test_session_local


def _seed_stock_and_run(session):
    session.add(Stock(symbol="TEST", company_name="Test Co", active=True))
    session.add(ScanRun(status="COMPLETED"))
    session.commit()
    return session.query(ScanRun).one().id


def _make_pending_recommendation(session, run_id, signal_date):
    rec = Recommendation(
        run_id=run_id,
        symbol="TEST",
        recommendation_date=signal_date,
        setup_type="BREAKOUT",
        score=80.0,
        rank=1,
        market_regime="BULLISH",
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
        status="ENTRY_PENDING",
    )
    session.add(rec)
    session.commit()
    return rec.id


def test_entry_pending_fills_when_candle_overlaps_zone(test_session, monkeypatch):
    session = test_session()
    run_id = _seed_stock_and_run(session)
    signal_date = date.today() - timedelta(days=3)
    rec_id = _make_pending_recommendation(session, run_id, signal_date)
    session.close()

    provider = _FakeProvider(
        {
            "TEST": _candles(
                [(signal_date + timedelta(days=1), 100.5, 101.0, 100.0, 100.8)]
            )
        }
    )
    monkeypatch.setattr(daily_update_module, "YahooFinanceProvider", lambda: provider)

    daily_update_module.run_daily_update()

    session = test_session()
    rec = session.get(Recommendation, rec_id)
    assert rec.status == "ACTIVE"
    assert rec.outcome.entry_price == pytest.approx(100.5 * 1.0005)


def test_entry_pending_fills_using_todays_own_candle(test_session, monkeypatch):
    """Regression test: yfinance's `end` param is exclusive, so a naive
    `end=date.today()` would silently drop today's own candle even though
    it has already closed by the time this job runs in the evening.
    """
    session = test_session()
    run_id = _seed_stock_and_run(session)
    signal_date = date.today() - timedelta(days=3)
    rec_id = _make_pending_recommendation(session, run_id, signal_date)
    session.close()

    provider = _FakeProvider(
        {"TEST": _candles([(date.today(), 100.5, 101.0, 100.0, 100.8)])}
    )
    monkeypatch.setattr(daily_update_module, "YahooFinanceProvider", lambda: provider)

    daily_update_module.run_daily_update()

    session = test_session()
    rec = session.get(Recommendation, rec_id)
    assert rec.status == "ACTIVE"


def test_entry_pending_stops_out_same_day_as_fill(test_session, monkeypatch):
    """Regression test: a fill and a stop-out can land in the same candle
    batch (e.g. the entry day itself gaps down through the stop) - this must
    be caught immediately rather than left as ACTIVE until tomorrow's run.
    """
    session = test_session()
    run_id = _seed_stock_and_run(session)
    signal_date = date.today() - timedelta(days=3)
    rec_id = _make_pending_recommendation(session, run_id, signal_date)
    session.close()

    provider = _FakeProvider(
        {
            "TEST": _candles(
                # entry zone is 100.0-101.0, stop_loss is 95.0 - this single
                # candle overlaps the entry zone on open and then breaches
                # the stop before close.
                [(signal_date + timedelta(days=1), 100.5, 101.0, 90.0, 92.0)]
            )
        }
    )
    monkeypatch.setattr(daily_update_module, "YahooFinanceProvider", lambda: provider)

    daily_update_module.run_daily_update()

    session = test_session()
    rec = session.get(Recommendation, rec_id)
    assert rec.status == "STOPPED_OUT"
    assert rec.outcome.entry_price == pytest.approx(100.5 * 1.0005)
    assert rec.outcome.exit_reason == "STOPPED_OUT"
    assert rec.outcome.net_pnl < 0


def test_entry_pending_expires_after_window(test_session, monkeypatch):
    session = test_session()
    run_id = _seed_stock_and_run(session)
    signal_date = date.today() - timedelta(days=10)
    rec_id = _make_pending_recommendation(session, run_id, signal_date)
    session.close()

    # 6 non-overlapping days (entry_expiry_days default is 5) - never fills
    provider = _FakeProvider(
        {
            "TEST": _candles(
                [
                    (signal_date + timedelta(days=i), 90.0, 91.0, 89.0, 90.5)
                    for i in range(1, 7)
                ]
            )
        }
    )
    monkeypatch.setattr(daily_update_module, "YahooFinanceProvider", lambda: provider)

    daily_update_module.run_daily_update()

    session = test_session()
    rec = session.get(Recommendation, rec_id)
    assert rec.status == "EXPIRED"


def test_active_position_with_no_new_data_still_reports_known_fields(
    test_session, monkeypatch
):
    """Regression test: when there's no new candle since entry (e.g. the
    position was entered earlier today and no new trading day has passed),
    only current_price/mark-to-market is genuinely unknown - entry price,
    quantity, stop-loss, and targets are already known from the DB and must
    still be reported rather than blanked out as N/A.
    """
    from app.core.config import get_strategy_config

    session = test_session()
    run_id = _seed_stock_and_run(session)
    signal_date = date.today() - timedelta(days=1)
    rec_id = _make_pending_recommendation(session, run_id, signal_date)
    session.add(
        RecommendationOutcome(
            recommendation_id=rec_id, entry_price=100.5, entry_date=date.today()
        )
    )
    session.get(Recommendation, rec_id).status = "ACTIVE"
    session.commit()

    rec = session.get(Recommendation, rec_id)
    provider = _FakeProvider({})  # no candles at all -> "no new data yet"
    config = get_strategy_config()

    result = daily_update_module._resolve_active(
        rec, provider, config.backtest, config.costs
    )

    assert result["status"] == "HOLD"
    assert result["detail"] == "no new data yet"
    assert result["entry_price"] == 100.5
    assert result["quantity"] == rec.quantity
    assert result["stop_loss"] == rec.stop_loss
    assert result["target_1"] == rec.target_1
    assert result["target_2"] == rec.target_2
    assert "current_price" not in result


def test_active_position_stops_out(test_session, monkeypatch):
    session = test_session()
    run_id = _seed_stock_and_run(session)
    signal_date = date.today() - timedelta(days=10)
    rec_id = _make_pending_recommendation(session, run_id, signal_date)
    entry_date = signal_date + timedelta(days=1)
    session.add(
        RecommendationOutcome(
            recommendation_id=rec_id, entry_price=100.5, entry_date=entry_date
        )
    )
    session.get(Recommendation, rec_id).status = "ACTIVE"
    session.commit()
    session.close()

    provider = _FakeProvider(
        {
            "TEST": _candles(
                [
                    (entry_date + timedelta(days=1), 99.0, 100.0, 90.0, 91.0)
                ]  # breaches stop
            )
        }
    )
    monkeypatch.setattr(daily_update_module, "YahooFinanceProvider", lambda: provider)

    daily_update_module.run_daily_update()

    session = test_session()
    rec = session.get(Recommendation, rec_id)
    assert rec.status == "STOPPED_OUT"
    assert rec.outcome.exit_reason == "STOPPED_OUT"
    assert rec.outcome.net_pnl < 0


def test_active_position_holds_when_no_trigger(test_session, monkeypatch):
    session = test_session()
    run_id = _seed_stock_and_run(session)
    signal_date = date.today() - timedelta(days=10)
    rec_id = _make_pending_recommendation(session, run_id, signal_date)
    entry_date = signal_date + timedelta(days=1)
    session.add(
        RecommendationOutcome(
            recommendation_id=rec_id, entry_price=100.5, entry_date=entry_date
        )
    )
    session.get(Recommendation, rec_id).status = "ACTIVE"
    session.commit()
    session.close()

    provider = _FakeProvider(
        {
            "TEST": _candles(
                [
                    (entry_date + timedelta(days=1), 101.0, 103.0, 100.0, 102.0)
                ]  # neither hit
            )
        }
    )
    monkeypatch.setattr(daily_update_module, "YahooFinanceProvider", lambda: provider)

    daily_update_module.run_daily_update()

    session = test_session()
    rec = session.get(Recommendation, rec_id)
    assert rec.status == "ACTIVE"
    assert rec.outcome.exit_date is None


def test_closed_digest_entry_reuses_persisted_outcome():
    rec = Recommendation(symbol="CLOSED", quantity=20, stop_loss=45.0, target_1=60.0, target_2=65.0)
    rec.outcome = RecommendationOutcome(
        entry_price=50.5, exit_price=45.2, exit_reason="STOPPED_OUT", net_pnl=-111.0
    )

    entry = daily_update_module._closed_digest_entry(rec)

    assert entry == {
        "symbol": "CLOSED",
        "status": "STOPPED_OUT",
        "detail": "exit at Rs.45.20, net P&L Rs.-111.00",
        "entry_price": 50.5,
        "current_price": 45.2,
        "quantity": 20,
        "stop_loss": 45.0,
        "target_1": 60.0,
        "target_2": 65.0,
        "net_pnl": -111.0,
    }


def test_closed_digest_entry_returns_none_when_never_filled():
    rec = Recommendation(symbol="NEVER", quantity=10)
    rec.outcome = None
    assert daily_update_module._closed_digest_entry(rec) is None


def test_daily_update_keeps_current_cohorts_closed_positions_in_digest(
    test_session, monkeypatch
):
    """A position that already stopped out (or hit target) in an earlier run
    must keep appearing in later daily digests for the rest of its cohort's
    cycle - the capital invested there is real and belongs in the overall
    invested/P&L picture, not just what's still open today.
    """
    session = test_session()
    run_id = _seed_stock_and_run(session)

    # a still-open recommendation in the same cohort (run_id)
    _make_pending_recommendation(session, run_id, date.today() - timedelta(days=1))

    session.add(Stock(symbol="CLOSED", company_name="Closed Co", active=True))
    closed_rec = Recommendation(
        run_id=run_id,
        symbol="CLOSED",
        recommendation_date=date.today() - timedelta(days=1),
        setup_type="BREAKOUT",
        score=80.0,
        rank=2,
        market_regime="BULLISH",
        current_price=50.0,
        entry_low=50.0,
        entry_high=51.0,
        stop_loss=45.0,
        target_1=60.0,
        target_2=65.0,
        risk_reward=2.0,
        quantity=20,
        capital_required=1000.0,
        max_loss=100.0,
        status="STOPPED_OUT",
    )
    session.add(closed_rec)
    session.commit()
    session.add(
        RecommendationOutcome(
            recommendation_id=closed_rec.id,
            entry_price=50.5,
            entry_date=date.today() - timedelta(days=1),
            exit_price=45.2,
            exit_date=date.today(),
            exit_reason="STOPPED_OUT",
            gross_pnl=-106.0,
            charges=5.0,
            net_pnl=-111.0,
            return_pct=-11.0,
            holding_days=1,
        )
    )
    session.commit()
    session.close()

    captured = {}
    monkeypatch.setattr(
        daily_update_module, "_send_daily_digest", lambda digest: captured.update(digest=digest)
    )
    monkeypatch.setattr(
        daily_update_module, "YahooFinanceProvider", lambda: _FakeProvider({})
    )

    daily_update_module.run_daily_update()

    digest = captured["digest"]
    closed_entry = next(e for e in digest if e["symbol"] == "CLOSED")
    assert closed_entry["status"] == "STOPPED_OUT"
    assert closed_entry["net_pnl"] == -111.0
    assert closed_entry["entry_price"] == 50.5
    assert closed_entry["current_price"] == 45.2


def test_idempotency_guard_skips_second_run_same_day(test_session, monkeypatch):
    session = test_session()
    _seed_stock_and_run(session)
    session.close()

    monkeypatch.setattr(
        daily_update_module, "YahooFinanceProvider", lambda: _FakeProvider({})
    )

    daily_update_module.run_daily_update()
    daily_update_module.run_daily_update()

    session = test_session()
    assert session.query(DailyUpdateRun).count() == 1


def test_terminal_positions_are_not_reprocessed(test_session, monkeypatch):
    session = test_session()
    run_id = _seed_stock_and_run(session)
    rec_id = _make_pending_recommendation(session, run_id, date.today())
    session.get(Recommendation, rec_id).status = "STOPPED_OUT"
    session.commit()
    session.close()

    monkeypatch.setattr(
        daily_update_module, "YahooFinanceProvider", lambda: _FakeProvider({})
    )

    daily_update_module.run_daily_update()

    session = test_session()
    run = session.query(DailyUpdateRun).one()
    assert run.positions_checked == 0
