from datetime import date, timedelta

from app.core.logging import get_logger, setup_logging
from app.data.yahoo_finance import YahooFinanceProvider
from app.db.models import Candle, Stock
from app.db.session import SessionLocal

setup_logging()
logger = get_logger(__name__)


def download_history(lookback_days: int = 730):
    db = SessionLocal()
    provider = YahooFinanceProvider()

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    try:
        stocks = db.query(Stock).filter(Stock.active).all()
        logger.info(
            f"Downloading history for {len(stocks)} active stocks from {start_date} to {end_date}"
        )

        for stock in stocks:
            logger.info(f"Fetching data for {stock.symbol}")
            try:
                df = provider.get_ohlcv(stock.symbol, start=start_date, end=end_date)
                if df.empty:
                    logger.warning(f"No data returned for {stock.symbol}")
                    continue

                # Check for existing records to avoid duplicates
                existing_dates_query = db.query(Candle.timestamp).filter(
                    Candle.symbol == stock.symbol, Candle.timestamp >= start_date
                )
                existing_dates = {r[0] for r in existing_dates_query.all()}

                new_candles = []
                for _, row in df.iterrows():
                    ts = row["timestamp"]
                    # Validation
                    if (
                        row["low"] > row["high"]
                        or row["open"] > row["high"]
                        or row["open"] < row["low"]
                        or row["close"] > row["high"]
                        or row["close"] < row["low"]
                    ):
                        logger.warning(
                            f"Invalid OHLC for {stock.symbol} on {ts}. Skipping."
                        )
                        continue
                    if row["volume"] < 0:
                        logger.warning(
                            f"Invalid volume for {stock.symbol} on {ts}. Skipping."
                        )
                        continue

                    if ts not in existing_dates:
                        candle = Candle(
                            symbol=stock.symbol,
                            timestamp=ts,
                            open=row["open"],
                            high=row["high"],
                            low=row["low"],
                            close=row["close"],
                            volume=row["volume"],
                            adjusted_close=row["adjusted_close"],
                            source="yahoo_finance",
                        )
                        new_candles.append(candle)

                if new_candles:
                    db.bulk_save_objects(new_candles)
                    db.commit()
                    logger.info(
                        f"Saved {len(new_candles)} new candles for {stock.symbol}"
                    )
                else:
                    logger.info(f"No new candles to save for {stock.symbol}")

            except Exception as e:
                logger.error(f"Error processing {stock.symbol}: {e}")
                db.rollback()

    finally:
        db.close()


if __name__ == "__main__":
    download_history()
