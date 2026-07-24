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
2. Ranks the whole universe by an explainable momentum score (multi-timeframe
   returns, moving-average structure, RSI band, volume expansion, distance from
   the 52-week high) — every factor's point contribution is shown.
3. Enters the top qualifying candidate **once per calendar day**, sizing the
   position at `deploy_fraction` of settled cash with room for `max_positions`.
4. Book-keeps everything in `data/momentum_trader.db` and publishes:
   - `docs/momentum_trader.html` — live dashboard (equity curve, open positions,
     closed trades, momentum leaderboard, return vs a `SPY` buy-and-hold benchmark)
   - `docs/momentum_email.html` + subject — the twice-daily email summary

**Risk profiles** (edit `config/momentum_trader.yml`):

| Profile      | Deploy/entry | Initial stop | Trail | Target | Min score | Max positions |
|--------------|-------------:|-------------:|------:|-------:|----------:|--------------:|
| conservative |          25% |           6% |    5% |   2.5R |       6.0 |             3 |
| normal       |          50% |           8% |    6% |   2.5R |       4.0 |             3 |
| degen        |         100% |          12% |    8% |   3.0R |       2.0 |             1 |

Runs on the same open/close schedule via `.github/workflows/momentum_trader.yml`,
and is live at `https://YOUR_USERNAME.github.io/market-scanner/momentum_trader.html`.

Tests for the scoring and risk math: `python tests/test_momentum_trader.py`.

## Not Financial Advice

This tool generates algorithmic signals based on price action and momentum. The
Momentum Trader is a **paper (simulated) portfolio** — fills are booked at daily
closing prices and ignore slippage, spreads, and fees. Everything here is for
informational and educational purposes only. Always do your own due diligence
before trading.
