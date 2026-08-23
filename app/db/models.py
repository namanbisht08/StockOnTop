from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True, nullable=False)
    company_name = Column(String, nullable=False)
    exchange = Column(String, nullable=False, default="NSE")
    sector = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    isin = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candles = relationship("Candle", back_populates="stock")
    indicators = relationship("Indicator", back_populates="stock")


class Candle(Base):
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, ForeignKey("stocks.symbol"), index=True, nullable=False)
    timestamp = Column(Date, index=True, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    adjusted_close = Column(Float, nullable=False)
    source = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    stock = relationship("Stock", back_populates="candles")


class Indicator(Base):
    __tablename__ = "indicators"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, ForeignKey("stocks.symbol"), index=True, nullable=False)
    timestamp = Column(Date, index=True, nullable=False)
    sma20 = Column(Float, nullable=True)
    sma50 = Column(Float, nullable=True)
    sma200 = Column(Float, nullable=True)
    ema20 = Column(Float, nullable=True)
    ema50 = Column(Float, nullable=True)
    rsi14 = Column(Float, nullable=True)
    macd = Column(Float, nullable=True)
    adx = Column(Float, nullable=True)
    atr14 = Column(Float, nullable=True)
    relative_volume = Column(Float, nullable=True)
    return_20d = Column(Float, nullable=True)
    return_60d = Column(Float, nullable=True)
    relative_strength_20d = Column(Float, nullable=True)
    relative_strength_60d = Column(Float, nullable=True)

    stock = relationship("Stock", back_populates="indicators")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("scan_runs.id"), nullable=False)
    symbol = Column(String, ForeignKey("stocks.symbol"), nullable=False)
    recommendation_date = Column(Date, index=True, nullable=False)
    setup_type = Column(String, nullable=False)
    score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)
    market_regime = Column(String, nullable=False)
    current_price = Column(Float, nullable=False)
    entry_low = Column(Float, nullable=False)
    entry_high = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    target_1 = Column(Float, nullable=False)
    target_2 = Column(Float, nullable=False)
    risk_reward = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    capital_required = Column(Float, nullable=False)
    max_loss = Column(Float, nullable=False)
    status = Column(String, default="WATCHLIST")
    ai_explanation = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    scan_run = relationship("ScanRun", back_populates="recommendations")
    outcome = relationship(
        "RecommendationOutcome", back_populates="recommendation", uselist=False
    )


class RecommendationOutcome(Base):
    __tablename__ = "recommendation_outcomes"

    id = Column(Integer, primary_key=True, index=True)
    recommendation_id = Column(
        Integer, ForeignKey("recommendations.id"), nullable=False
    )
    entry_price = Column(Float, nullable=True)
    entry_date = Column(Date, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_date = Column(Date, nullable=True)
    exit_reason = Column(String, nullable=True)
    gross_pnl = Column(Float, nullable=True)
    charges = Column(Float, nullable=True)
    net_pnl = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)

    recommendation = relationship("Recommendation", back_populates="outcome")


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    universe_size = Column(Integer, nullable=True)
    data_valid = Column(Integer, nullable=True)
    filtered_count = Column(Integer, nullable=True)
    candidate_count = Column(Integer, nullable=True)
    final_count = Column(Integer, nullable=True)
    market_regime = Column(String, nullable=True)
    status = Column(String, nullable=False)
    error_message = Column(String, nullable=True)

    recommendations = relationship("Recommendation", back_populates="scan_run")


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, ForeignKey("stocks.symbol"), nullable=False)
    published_at = Column(DateTime, nullable=False)
    title = Column(String, nullable=False)
    source = Column(String, nullable=False)
    url = Column(String, nullable=False)
    sentiment = Column(String, nullable=True)
    risk_level = Column(String, nullable=True)
    summary = Column(String, nullable=True)
