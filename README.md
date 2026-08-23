# AI-Powered Indian Stock Swing Trading System

A production-ready personal swing-trading research and decision-support system for Indian equities.

## Features

- **Indian Equities:** Focused on NSE stocks.
- **Automated Scanning:** Evaluates the stock universe based on deterministic technical and fundamental criteria.
- **Risk Management:** Calculates precise entry, stop-loss, targets, and position sizing.
- **AI Context:** Integrates LLM to explain the trade thesis based on deterministic data and recent news.
- **Notifications:** Weekly reports generated and sent via Telegram.
- **Backtesting & Paper Trading:** Tools to evaluate strategy performance historically and on live data without real money.

## Setup

1. **Install dependencies:**
   ```bash
   make install
   ```
2. **Setup environment:**
   Copy `.env.example` to `.env` and fill in necessary values.
3. **Run database migrations:**
   ```bash
   make migrate
   ```
4. **Seed the database:**
   ```bash
   make seed
   ```

## Workflow

To run a scan manually:
```bash
make weekly-scan
```

To run a historical backtest:
```bash
PYTHONPATH=. python scripts/run_backtest.py --start 2023-01-01 --end 2024-01-01 --output backtests/result.json
```
Add `--data-dir path/to/csv` to replay from local CSV fixtures (via `CSVProvider`)
instead of hitting `yfinance`.

### Backtesting assumptions

The backtester (`app/backtest/`) walks forward one decision date per calendar
week, truncating each symbol's history to that date before recomputing
indicators, so nothing after the decision date can influence a signal. A
selected candidate's outcome is then resolved from the real candles that
follow. Notable simplifications, documented in code where they matter most:

- Entry fills within `backtest.entry_expiry_days` if a candle's range
  overlaps the entry zone; a gap beyond `extended_entry_pct` is treated as a
  missed entry rather than chased.
- A trade closes fully at target_1 (no partial booking toward target_2).
- If a candle's range touches both the stop and target in the same session,
  the stop is assumed to fill first.
- Transaction cost rates in `config/strategy.yaml` (`costs:`) are
  illustrative placeholders — verify against current SEBI/exchange/broker
  rates before relying on them beyond research-grade backtesting.
- Reported CAGR/drawdown/Sharpe are computed off a realized-P&L equity curve
  (capital + cumulative net P&L by exit date), not a daily mark-to-market
  curve, so they understate intra-period volatility when multiple positions
  are open at once.

## Deployment

Runs on a persistent Docker host (not the plan's default GitHub-Actions/local-
cron path - see note below) so the SQLite database survives between runs:

```bash
docker compose build app
docker compose up -d app          # starts the FastAPI app (GET /health)
docker compose exec app alembic upgrade head
docker compose exec app python scripts/seed_universe.py
docker compose exec app python scripts/download_history.py
docker compose exec app python scripts/run_weekly_scan.py
```

A host crontab runs `weekly_run.sh` (download fresh data, then scan) every
Sunday at 12:30 UTC / 18:00 IST, logging to `logs/weekly.log`. `run_weekly_scan`
has an idempotency guard - a duplicate trigger the same day is a no-op rather
than a duplicate recommendation or a second Telegram message.

Notes:
- `.env` holds real secrets and is never committed; it's copied to the host
  out-of-band (scp), not via git.
- The Ollama service in `docker-compose.yml` is opt-in (`--profile ollama`) -
  Gemini is the primary LLM provider, and the app degrades to a
  deterministic-only report if no provider is reachable, so a small instance
  isn't forced to run an idle local-LLM container.
- Port 8000 (the health endpoint) is only reachable from inside the host/VPC,
  not the public internet - deliberate, since the plan calls for no public
  endpoints in v1.
- This deviates from the plan's ₹0/month default: a persistent cloud instance
  running 24/7 has a real (small) cost, unlike GitHub Actions' free tier or
  a machine you already own. Chosen here to sidestep GitHub Actions' ephemeral
  runners (a fresh SQLite DB every run) without giving up scheduled execution.

## Milestone Status

- [x] Milestone 1 — Project foundation
- [x] Milestone 2 — Market data
- [x] Milestone 3 — Indicators
- [x] Milestone 4 — Strategy
- [x] Milestone 5 — Risk
- [x] Milestone 6 — Backtesting
- [x] Milestone 7 — AI (LLM abstraction, structured explanations, failure fallback
      done; news summarization via GDELT/NSE filings not yet built)
- [x] Milestone 8 — Reporting (text report + Telegram delivery + recommendation
      persistence done; HTML report and email are optional/deferred per the plan)
- [ ] Milestone 9 — Paper trading
- [x] Milestone 10 — Production execution (weekly cron on a persistent Docker
      host, per the Deployment section above - a paid instance rather than the
      plan's ₹0/month GitHub-Actions/local-cron default, see notes above)

## Disclaimer
This is a research/decision-support system, not an automated trading bot. Real-money trading should begin only after adequate backtesting and paper trading.
