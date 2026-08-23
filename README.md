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

## Milestone Status

- [x] Milestone 1 — Project foundation
- [x] Milestone 2 — Market data
- [x] Milestone 3 — Indicators
- [x] Milestone 4 — Strategy
- [x] Milestone 5 — Risk
- [x] Milestone 6 — Backtesting
- [ ] Milestone 7 — AI
- [ ] Milestone 8 — Reporting
- [ ] Milestone 9 — Paper trading
- [ ] Milestone 10 — Free production execution

## Disclaimer
This is a research/decision-support system, not an automated trading bot. Real-money trading should begin only after adequate backtesting and paper trading.
