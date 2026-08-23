import argparse
import json
from dataclasses import asdict
from datetime import date, timedelta

from app.backtest.engine import run_backtest
from app.backtest.metrics import calculate_metrics
from app.core.config import get_settings, get_strategy_config
from app.core.logging import get_logger, setup_logging
from app.data.csv_provider import CSVProvider
from app.data.yahoo_finance import YahooFinanceProvider
from app.db.models import Stock
from app.db.session import SessionLocal

setup_logging()
logger = get_logger(__name__)

INDEX_SYMBOL = "^NSEI"
INDICATOR_WARMUP_DAYS = 320  # ~210 trading days of buffer before start_date


def parse_args():
    parser = argparse.ArgumentParser(description="Run the swing-trading backtest")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="If set, load OHLCV from CSVProvider(data_dir) instead of yfinance",
    )
    parser.add_argument(
        "--output", default=None, help="Optional path to write JSON results"
    )
    return parser.parse_args()


def run(start: date, end: date, data_dir: str = None, output: str = None) -> dict:
    config = get_strategy_config()
    fetch_start = start - timedelta(days=INDICATOR_WARMUP_DAYS)

    provider = CSVProvider(data_dir) if data_dir else YahooFinanceProvider()

    db = SessionLocal()
    try:
        symbols = [s.symbol for s in db.query(Stock).filter(Stock.active).all()]
    finally:
        db.close()

    if not symbols:
        logger.error("No active symbols in the universe; run `make seed` first")
        return {}

    logger.info(f"Fetching index history for {INDEX_SYMBOL}")
    index_history = provider.get_index_data(INDEX_SYMBOL, fetch_start, end)
    if index_history.empty:
        logger.error(f"No index data available for {INDEX_SYMBOL}")
        return {}

    stock_history = {}
    for symbol in symbols:
        logger.info(f"Fetching history for {symbol}")
        df = provider.get_ohlcv(symbol, fetch_start, end)
        if df.empty:
            logger.warning(f"No history for {symbol}; skipping")
            continue
        stock_history[symbol] = df

    logger.info(
        f"Running backtest over {len(stock_history)} symbols from {start} to {end}"
    )
    trades = run_backtest(stock_history, index_history, start, end)
    metrics = calculate_metrics(trades, config.portfolio.capital)

    result = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "symbols": list(stock_history.keys()),
        "trades": [
            {**asdict(t), "signal_date": t.signal_date.isoformat()} for t in trades
        ],
        "metrics": asdict(metrics),
    }

    for trade in result["trades"]:
        for field in ("entry_date", "exit_date"):
            if trade[field] is not None:
                trade[field] = trade[field].isoformat()

    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(f"Results written to {output}")

    logger.info(f"Metrics: {metrics}")
    return result


if __name__ == "__main__":
    args = parse_args()
    get_settings()
    run(
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        data_dir=args.data_dir,
        output=args.output,
    )
