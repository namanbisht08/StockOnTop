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

## Milestone Status

- [x] Milestone 1 — Project foundation
- [x] Milestone 2 — Market data
- [x] Milestone 3 — Indicators
- [x] Milestone 4 — Strategy
- [x] Milestone 5 — Risk
- [ ] Milestone 6 — Backtesting
- [ ] Milestone 7 — AI
- [ ] Milestone 8 — Reporting
- [ ] Milestone 9 — Paper trading
- [ ] Milestone 10 — Free production execution

## Disclaimer
This is a research/decision-support system, not an automated trading bot. Real-money trading should begin only after adequate backtesting and paper trading.
