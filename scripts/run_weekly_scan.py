from app.core.logging import setup_logging
from app.jobs.weekly_scan import run_weekly_scan

if __name__ == "__main__":
    setup_logging()
    run_weekly_scan()
