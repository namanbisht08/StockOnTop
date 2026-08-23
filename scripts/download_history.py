from datetime import date, timedelta

from app.core.logging import get_logger, setup_logging
from app.data.yahoo_finance import YahooFinanceProvider
from app.db.models import Candle, Stock
from app.db.session import SessionLocal

setup_logging()
logger = get_logger(__name__)

INDEX_SYMBOL = "^NSEI"


def _ensure_index_stock_row(db) -> None:
    """Market regime detection (app/strategy/market_regime.py) needs NIFTY
    candles in the same `candles` table as every other symbol, and
    Candle.symbol is a real foreign key into stocks.symbol - so the index
    needs its own (inactive, non-tradeable) Stock row before its candles can
    be inserted.
    """
    existing = db.query(Stock).filter(Stock.symbol == INDEX_SYMBOL).first()
    if existing is None:
        db.add(
            Stock(
                symbol=INDEX_SYMBOL,
                company_name="NIFTY 50 Index",
                exchange="NSE",
                sector=None,
                active=False,
            )
        )
        db.commit()


def _download_symbol(
    db, provider, symbol: str, start_date: date, end_date: date
) -> None:
    logger.info(f"Fetching data for {symbol}")
    try:
        df = provider.get_ohlcv(symbol, start=start_date, end=end_date)
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return

        existing_dates_query = db.query(Candle.timestamp).filter(
            Candle.symbol == symbol, Candle.timestamp >= start_date
        )
        existing_dates = {r[0] for r in existing_dates_query.all()}

        new_candles = []
        for _, row in df.iterrows():
            ts = row["timestamp"]
            if (
                row["low"] > row["high"]
                or row["open"] > row["high"]
                or row["open"] < row["low"]
                or row["close"] > row["high"]
                or row["close"] < row["low"]
            ):
                logger.warning(f"Invalid OHLC for {symbol} on {ts}. Skipping.")
                continue
            if row["volume"] < 0:
                logger.warning(f"Invalid volume for {symbol} on {ts}. Skipping.")
                continue

            if ts not in existing_dates:
                new_candles.append(
                    Candle(
                        symbol=symbol,
                        timestamp=ts,
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                        adjusted_close=row["adjusted_close"],
                        source="yahoo_finance",
                    )
                )

        if new_candles:
            db.bulk_save_objects(new_candles)
            db.commit()
            logger.info(f"Saved {len(new_candles)} new candles for {symbol}")
        else:
            logger.info(f"No new candles to save for {symbol}")

    except Exception as e:
        logger.error(f"Error processing {symbol}: {e}")
        db.rollback()


def download_history(lookback_days: int = 730):
    db = SessionLocal()
    provider = YahooFinanceProvider()

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    try:
        _ensure_index_stock_row(db)

        stocks = db.query(Stock).filter(Stock.active).all()
        symbols = [s.symbol for s in stocks]
        if INDEX_SYMBOL not in symbols:
            symbols.append(INDEX_SYMBOL)

        logger.info(
            f"Downloading history for {len(symbols)} symbols from {start_date} to {end_date}"
        )

        for symbol in symbols:
            _download_symbol(db, provider, symbol, start_date, end_date)

    finally:
        db.close()


if __name__ == "__main__":
    download_history()
