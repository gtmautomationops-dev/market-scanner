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

## Not Financial Advice

This tool generates algorithmic signals based on price action and momentum. It is for informational purposes only. Always do your own due diligence before trading.
