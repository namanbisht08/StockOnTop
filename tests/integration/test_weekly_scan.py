from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.jobs.weekly_scan as weekly_scan_module
from app.ai.provider import MockLLMProvider
from app.db.models import Base, Candle, Recommendation, ScanRun, Stock


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """.env now holds live Telegram/Gemini credentials - any test that fails
    to mock its dependencies must fail loudly rather than silently making a
    real network call.
    """

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected real HTTP call in a weekly_scan test")

    monkeypatch.setattr(httpx, "post", _fail)


@pytest.fixture
def test_session(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    test_session_local = sessionmaker(bind=engine)
    monkeypatch.setattr(weekly_scan_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(
        weekly_scan_module, "build_default_providers", lambda: [MockLLMProvider()]
    )
    return test_session_local


def _seed_flat_index(session, n=210):
    price = 20000.0
    for i in range(n):
        ts = date(2023, 1, 1) + timedelta(days=i)
        price += 1.0
        session.add(
            Candle(
                symbol="^NSEI",
                timestamp=ts,
                open=price,
                high=price + 5,
                low=price - 5,
                close=price,
                volume=0,
                adjusted_close=price,
                source="test",
            )
        )
    session.commit()


def test_no_qualifying_stocks_completes_as_no_trade(test_session, monkeypatch):
    session = test_session()
    _seed_flat_index(session)
    session.add(Stock(symbol="TEST", company_name="Test Co", active=True))
    # Deliberately no candles for TEST - it must be skipped, not crash the run.
    session.commit()
    session.close()

    monkeypatch.setattr(
        weekly_scan_module,
        "get_settings",
        lambda: type("S", (), {"telegram_bot_token": None, "telegram_chat_id": None})(),
    )

    weekly_scan_module.run_weekly_scan()

    session = test_session()
    runs = session.query(ScanRun).all()
    assert len(runs) == 1
    assert runs[0].status == "COMPLETED"
    assert runs[0].final_count == 0
    assert session.query(Recommendation).count() == 0


def test_idempotency_guard_skips_second_run_same_day(test_session, monkeypatch):
    session = test_session()
    _seed_flat_index(session)
    session.commit()
    session.close()

    monkeypatch.setattr(
        weekly_scan_module,
        "get_settings",
        lambda: type("S", (), {"telegram_bot_token": None, "telegram_chat_id": None})(),
    )

    weekly_scan_module.run_weekly_scan()
    weekly_scan_module.run_weekly_scan()

    session = test_session()
    assert session.query(ScanRun).filter(ScanRun.status == "COMPLETED").count() == 1


def test_symbol_with_open_position_is_skipped_and_not_duplicated(
    test_session, monkeypatch
):
    session = test_session()
    _seed_flat_index(session)
    session.add(Stock(symbol="OPEN1", company_name="Already Open", active=True))
    scan_run = ScanRun(status="COMPLETED")
    session.add(scan_run)
    session.commit()
    session.add(
        Recommendation(
            run_id=scan_run.id,
            symbol="OPEN1",
            recommendation_date=date.today() - timedelta(days=2),
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
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        weekly_scan_module,
        "get_settings",
        lambda: type("S", (), {"telegram_bot_token": None, "telegram_chat_id": None})(),
    )

    weekly_scan_module.run_weekly_scan()

    session = test_session()
    # still exactly one recommendation for OPEN1 - the scan must not have
    # re-evaluated or duplicated a symbol it's already tracking.
    assert (
        session.query(Recommendation).filter(Recommendation.symbol == "OPEN1").count()
        == 1
    )


def test_insufficient_index_history_defaults_to_neutral_and_still_completes(
    test_session, monkeypatch
):
    session = test_session()
    session.add(Stock(symbol="TEST", company_name="Test Co", active=True))
    session.commit()
    session.close()

    monkeypatch.setattr(
        weekly_scan_module,
        "get_settings",
        lambda: type("S", (), {"telegram_bot_token": None, "telegram_chat_id": None})(),
    )

    weekly_scan_module.run_weekly_scan()

    session = test_session()
    run = session.query(ScanRun).one()
    assert run.status == "COMPLETED"
    assert run.market_regime == "NEUTRAL"
