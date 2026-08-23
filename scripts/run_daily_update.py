from app.core.logging import setup_logging
from app.jobs.daily_update import run_daily_update

if __name__ == "__main__":
    setup_logging()
    run_daily_update()
