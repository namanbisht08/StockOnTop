import sys
from pathlib import Path

import yaml

from app.core.logging import get_logger, setup_logging
from app.db.models import Stock
from app.db.session import SessionLocal

setup_logging()
logger = get_logger(__name__)


def seed_universe():
    config_path = Path("config/universe.yaml")
    if not config_path.exists():
        logger.error(f"Universe config not found at {config_path}")
        sys.exit(1)

    with open(config_path, "r") as f:
        data = yaml.safe_load(f)

    stocks_data = data.get("stocks", [])
    if not stocks_data:
        logger.warning("No stocks found in universe.yaml")
        return

    db = SessionLocal()
    try:
        count = 0
        for stock_data in stocks_data:
            symbol = stock_data["symbol"]
            existing = db.query(Stock).filter(Stock.symbol == symbol).first()
            if not existing:
                new_stock = Stock(
                    symbol=symbol,
                    company_name=stock_data["company_name"],
                    sector=stock_data.get("sector"),
                    industry=stock_data.get("industry"),
                    active=True,
                )
                db.add(new_stock)
                count += 1
            else:
                existing.company_name = stock_data["company_name"]
                existing.sector = stock_data.get("sector")
                existing.active = True

        db.commit()
        logger.info(f"Successfully seeded {count} new stocks into the universe.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding universe: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_universe()
