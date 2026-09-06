# Market Scanner

Automated daily stock and ETF scanner for US and Canadian markets. Runs via GitHub Actions, publishes to GitHub Pages.

## What It Does

- Scans 300+ stocks and ETFs (US + Canada) twice daily at market open (9:35 AM ET) and close (4:05 PM ET)
- Calculates entry zones, stop losses, profit targets, and risk/reward ratios
- Generates an interactive HTML dashboard published to GitHub Pages
- Click any row to see full entry/exit analysis with thesis

## Setup (5 minutes)

1. Create a new GitHub repo (e.g., `market-scanner`)

2. Push this code:
```bash
cd market-scanner
git init
git add .
git commit -m "Initial scanner setup"
git remote add origin https://github.com/YOUR_USERNAME/market-scanner.git
git branch -M main
git push -u origin main
```

3. Enable GitHub Pages:
   - Go to repo Settings > Pages
   - Set Source to "Deploy from a branch"
   - Set Branch to `gh-pages` / `root`
   - Save

4. Trigger the first scan:
   - Go to Actions tab > "Market Scanner - Daily Scan" > "Run workflow"

5. Your dashboard will be live at:
   `https://YOUR_USERNAME.github.io/market-scanner/`

## Customizing

Edit the ticker lists at the top of `scripts/scanner.py` to add or remove instruments.

## Schedule

Runs Monday–Friday at:
- 9:35 AM ET (13:35 UTC) — shortly after market open
- 4:05 PM ET (20:05 UTC) — shortly after market close

To change the schedule, edit `.github/workflows/scan.yml`.

## Momentum Trader (paper portfolio)

A deterministic, one-pick-per-day momentum strategy that trades a **simulated**
cash account — no brokerage, no real money, no API keys. Inspired by
[ai-momentum-trader](https://github.com/merjua14/ai-momentum-trader), but rebuilt
to fit this repo: the reference bot's "AI decision layer" is replaced with a
transparent, reproducible momentum ranking, and execution is paper only.

Each run (`scripts/momentum_trader.py`):

1. Marks open positions to market and manages an ATR-based stop that arms to
   breakeven at `activate_pct` and then trails `trail_pct` under the peak
   (ratchets up only).
2. Ranks the whole universe by an explainable momentum score — every factor's
   point contribution is shown, sorted by impact:
   - multi-timeframe returns (1m / 3m / 6m)
   - moving-average structure (above 20/50/200-day, bullish stacking)
   - RSI band (rewards healthy momentum, penalizes overbought/dead)
   - volume expansion (is the move backed by participation?)
   - distance from the 52-week high
   - **relative strength vs SPY** — is it actually beating the market, or just
     drifting up with the tide?
   - **trend quality** — the R² of a log-price regression; smooth, persistent
     trends survive a trailing stop far better than jagged ones that whipsaw.
3. Enters the top qualifying candidate **once per calendar day**, sizing the
   position at `deploy_fraction` of settled cash with room for `max_positions`.
4. Book-keeps everything in `data/momentum_trader.db` and publishes:
   - `docs/momentum_trader.html` — live dashboard: equity curve with the `SPY`
     buy-and-hold line overlaid, open positions, closed trades, momentum
     leaderboard, and a **Performance** panel (max drawdown, profit factor,
     expectancy in R, avg win / avg loss, best / worst trade)
   - `docs/momentum_email.html` + subject — the twice-daily email summary

The main scanner dashboard (`index.html`) and the Momentum Trader dashboard link
to each other in the header.

**Risk profiles** (edit `config/momentum_trader.yml`):

| Profile      | Deploy/entry | Initial stop | Trail | Target | Min score | Max positions |
|--------------|-------------:|-------------:|------:|-------:|----------:|--------------:|
| conservative |          25% |           6% |    5% |   2.5R |       6.0 |             3 |
| normal       |          50% |           8% |    6% |   2.5R |       4.0 |             3 |
| degen        |         100% |          12% |    8% |   3.0R |       2.0 |             1 |

Runs on the same open/close schedule via `.github/workflows/momentum_trader.yml`,
and is live at `https://YOUR_USERNAME.github.io/market-scanner/momentum_trader.html`.

Tests for the scoring and risk math: `python tests/test_momentum_trader.py`.

## The Hedge-Fund Agents — Alex, Sarah & Elena

A three-agent "kitchen-table hedge fund" team, in the spirit of the WSJ piece
about running Claude analysts from your laptop. They are **advisory**: they
analyze, flag, and report — they never place an order.

They watch **two books**:

- **My Picks** — the book *you* control. Record your real (or tracked) lots in
  [`config/my_picks.yml`](config/my_picks.yml); the agents mark them to market,
  risk-check them, and report on them. They never edit that file.
- **Momentum** — the existing paper portfolio managed by `momentum_trader.py`,
  read straight from `data/momentum_trader.db`.

| Agent | Role | Runs | Output |
|-------|------|------|--------|
| **Alex** (`scripts/analyst_alex.py`) | Scans the market for promising stocks/ETFs and publishes a ranked watchlist with a thesis + entry/stop/target per idea. Skips names you already own; flags held names whose momentum is fading. | Open & close (9:40 AM / 4:10 PM ET) | `analyst_alex.html` + email |
| **Sarah** (`scripts/risk_sarah.py`) | Checks every open position in both books before the close and ranks a pre-close checklist: stops breached/near, targets hit/near, outsized losses, dead money, single-name concentration, book drawdown. Snapshots the My Picks book daily. | Pre-close (3:45 PM ET, weekdays) | `risk_sarah.html` + email |
| **Elena** (`scripts/report_elena.py`) | Writes the weekly performance report: combined P&L and return on capital vs SPY, this week's change, a per-book breakdown, and the biggest contributors and detractors. | Weekly (Fri 4:30 PM ET) | `report_elena.html` + email |
| **Marcus** (`scripts/flow_marcus.py`) | Scans options activity for big, aggressive trades, scores them, and surfaces the single highest-confidence setup with a **defined-risk** structure. Advisory. | Post-close (4:15 PM ET) | `flow_marcus.html` + email |

### Marcus & the options-flow data (read this)

Marcus is modeled on the WSJ "Codex options-flow" agent, but he is honest about
his data. On the default **`yfinance`** source he reads delayed, end-of-day
option-**chain** snapshots and scores the classic *unusual activity* tells —
volume vs open interest, premium notional, days-to-expiry, moneyness. A chain
**cannot** show sweeps, blocks, or which side hit the bid/ask, so this is a
labeled **proxy**, not true institutional flow. Real flow needs a paid feed
(Polygon.io, Unusual Whales); drop-in provider slots exist in
`scripts/flow_marcus.py` behind a `FlowProvider` interface — set `data_source`
in `config/flow_marcus.yml` and supply the key via the `FLOW_API_KEY` secret.

Marcus is advisory and every suggestion is framed as **defined risk**: a long
option can lose 100% of its premium. He never places an order.

Shared plumbing lives in `scripts/fund_common.py` (config/holdings loading, price
fetching, marking each book to market, Sarah's risk rules, the daily snapshot in
`data/hedge_fund.db`, and the shared dashboard chrome), reusing the momentum
engine and ticker universe so nothing drifts. Each dashboard links to the others.

**Getting started:** open `config/my_picks.yml`, add your lots under `holdings:`,
commit. The agents pick them up on their next run. Tune the thresholds in
`config/analyst_alex.yml`, `config/risk_sarah.yml`, and `config/report_elena.yml`.
They use the same `GMAIL_USERNAME` / `GMAIL_APP_PASSWORD` secrets and email
address as the rest of the repo.

Tests for the marking, risk-flag, and report math: `python tests/test_hedge_fund.py`.

## Not Financial Advice

This tool generates algorithmic signals based on price action and momentum. The
Momentum Trader is a **paper (simulated) portfolio** — fills are booked at daily
closing prices and ignore slippage, spreads, and fees. Everything here is for
informational and educational purposes only. Always do your own due diligence
before trading.
