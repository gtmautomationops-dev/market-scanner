#!/usr/bin/env python3
"""
Market Scanner - Automated daily scanner for US and Canadian markets.
Outputs docs/index.html for GitHub Pages deployment.
"""

import json
import time
from datetime import datetime
from pathlib import Path

import yfinance as yf

# ─── TICKER LISTS ─────────────────────────────────────────────────────────────

US_STOCKS = [
    # Technology
    "AAPL", "MSFT", "NVDA", "AMD", "INTC", "QCOM", "AVGO", "MU", "AMAT",
    "LRCX", "KLAC", "ASML", "ARM", "SMCI", "PLTR", "SNOW", "CRM", "NOW", "ORCL",
    "META", "GOOGL", "AMZN", "NFLX", "UBER", "ABNB", "SHOP", "SQ", "PYPL",
    "COIN", "MSTR", "HOOD", "RBLX", "TTD", "ZS", "CRWD", "PANW", "OKTA",
    "NET", "DDOG", "MDB", "CFLT", "GTLB", "SAMSF",
    # Energy
    "XOM", "CVX", "COP", "EOG", "DVN", "HAL", "SLB", "BKR", "MPC",
    "PSX", "VLO", "OXY", "APA", "FANG", "CTRA", "EQT", "AR", "RRC",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "USB", "PNC", "TFC", "COF",
    "AXP", "V", "MA", "BRK-B", "BLK", "SCHW", "ICE", "CME", "SPGI", "MCO",
    # Healthcare
    "JNJ", "PFE", "ABBV", "MRK", "LLY", "BMY", "AMGN", "GILD", "REGN", "VRTX",
    "ISRG", "MDT", "EW", "BDX", "DHR", "TMO", "IQV",
    # Industrials / Defense
    "GEV", "GE", "RTX", "LMT", "NOC", "BA", "HON", "CAT", "DE", "EMR",
    "ETN", "PH", "ROK", "AME", "FTV", "XYL", "TT",
    # Consumer
    "WMT", "TGT", "COST", "HD", "LOW", "TJX", "ROST", "NKE", "LULU",
    "MCD", "SBUX", "YUM", "CMG", "DPZ", "DRI",
    # REITs
    "AMT", "PLD", "CCI", "EQIX", "PSA", "EXR", "AVB", "EQR",
    # Materials
    "NEM", "FCX", "GOLD", "AA", "NUE", "RS",
    # Utilities
    "NEE", "SO", "DUK", "AEP", "D", "EXC", "XEL", "WEC", "AWK",
]

US_ETFS = [
    # Broad market
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VEA", "VWO",
    # Bonds
    "AGG", "BND", "TLT", "IEF", "SHY", "HYG", "JNK", "LQD", "EMB",
    # Sector
    "XLK", "XLE", "XLF", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    "SMH", "SOXX", "ARKK", "ARKG", "ARKF",
    # Dividend / Income
    "SCHD", "VYM", "DVY", "HDV", "NOBL", "VIG", "SDY", "DGRO",
    # Commodity
    "GLD", "SLV", "USO", "UNG", "PDBC",
    # International
    "EFA", "EEM", "FXI", "EWJ", "EWZ", "KWEB",
    # Leveraged
    "TQQQ", "SOXL", "UPRO",
]

CA_STOCKS = [
    # Banks
    "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "NA.TO", "EQB.TO",
    # Energy
    "CNQ.TO", "SU.TO", "CVE.TO", "ATH.TO", "MEG.TO", "BTE.TO", "ARX.TO",
    "TOU.TO", "WCP.TO", "BIR.TO", "ERF.TO", "CPG.TO",
    # Mining / Gold
    "ABX.TO", "AEM.TO", "WPM.TO", "KL.TO", "FNV.TO", "IMG.TO", "MAG.TO",
    # Tech
    "SHOP.TO", "CSU.TO", "TOI.TO", "LSPD.TO", "DCBO.TO",
    # Industrials / Rail
    "CNR.TO", "CP.TO", "WSP.TO", "STN.TO", "BYD.TO", "TIH.TO",
    # Telecom / Utilities
    "BCE.TO", "T.TO", "RCI-B.TO", "FTS.TO", "H.TO", "BEP-UN.TO",
    # Consumer / Retail
    "ATD.TO", "L.TO", "MRU.TO", "DOL.TO", "CTC-A.TO", "EMP-A.TO",
    # REITs
    "CAR-UN.TO", "REI-UN.TO", "AP-UN.TO", "HR-UN.TO",
    # Insurance / Other
    "MFC.TO", "SLF.TO", "GWO.TO", "FFH.TO", "POW.TO",
]

CA_ETFS = [
    # Broad
    "XIU.TO", "XIC.TO", "ZCN.TO", "VCN.TO", "HXT.TO",
    # Dividend
    "XDV.TO", "CDZ.TO", "VDY.TO", "ZWB.TO",
    # Sector
    "XEG.TO", "XFN.TO", "XGD.TO", "ZEB.TO",
    # US exposure (CAD-hedged)
    "XSP.TO", "ZSP.TO", "VSP.TO", "XQQ.TO", "ZQQ.TO",
    # Bond
    "XBB.TO", "ZAG.TO", "VAB.TO", "XSB.TO",
    # International
    "XEF.TO", "ZEA.TO", "VEE.TO",
    # All-in-one / Balanced
    "XGRO.TO", "XBAL.TO", "VGRO.TO", "VBAL.TO", "VCNS.TO",
    "XEQT.TO", "VEQT.TO", "ZEQT.TO",
]

ETF_SET = set(US_ETFS + CA_ETFS)


# ─── SIGNAL ENGINE ────────────────────────────────────────────────────────────

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        return 100.0
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def score_ticker(ticker, info, hist):
    try:
        if hist is None or len(hist) < 20:
            return None
        closes = list(hist["Close"].dropna())
        if len(closes) < 20:
            return None

        current = closes[-1]
        high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
        low_52w = min(closes[-252:]) if len(closes) >= 252 else min(closes)
        ytd_range = high_52w - low_52w

        range_pct = (current - low_52w) / (high_52w - low_52w) if high_52w != low_52w else 0.5
        rsi = calculate_rsi(closes[-60:] if len(closes) >= 60 else closes)
        ma20 = sum(closes[-20:]) / 20
        ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sum(closes) / len(closes)
        price_vs_ma20 = (current - ma20) / ma20 * 100
        price_vs_ma50 = (current - ma50) / ma50 * 100

        if "Volume" in hist.columns:
            volumes = list(hist["Volume"].dropna())
            vol_5d = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else volumes[-1]
            vol_20d = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else vol_5d
            vol_ratio = vol_5d / vol_20d if vol_20d > 0 else 1.0
        else:
            vol_ratio = 1.0

        score = 0
        factors = []

        if price_vs_ma50 > 5:
            score += 2
            factors.append("Above 50MA")
        elif price_vs_ma50 > 0:
            score += 1
            factors.append("Near 50MA")
        else:
            score -= 1
            factors.append("Below 50MA")

        if 40 <= rsi <= 65:
            score += 2
            factors.append(f"RSI {rsi:.0f}")
        elif rsi < 30:
            score += 1
            factors.append(f"RSI {rsi:.0f} oversold")
        elif rsi > 75:
            score -= 2
            factors.append(f"RSI {rsi:.0f} overbought")
        else:
            factors.append(f"RSI {rsi:.0f}")

        if range_pct < 0.35:
            score += 2
            factors.append("Near 52W low")
        elif range_pct > 0.85:
            score -= 1
            factors.append("Near 52W high")
        else:
            score += 1

        if vol_ratio > 1.3:
            score += 1
            factors.append("High volume")
        elif vol_ratio < 0.7:
            score -= 1
            factors.append("Low volume")

        if price_vs_ma20 > 10:
            score -= 1
            factors.append("Extended")
        elif price_vs_ma20 < -5:
            score += 1
            factors.append("Pullback")

        if score >= 4:
            signal, signal_class = "Strong Buy", "strong-buy"
        elif score >= 2:
            signal, signal_class = "Buy", "buy"
        elif score >= 0:
            signal, signal_class = "Hold", "hold"
        else:
            signal, signal_class = "Caution", "caution"

        if range_pct > 0.85 or price_vs_ma20 > 12:
            entry_low, entry_high = current * 0.85, current * 0.90
            setup = "pullback"
            alert = f"Enter on pullback to ${entry_high:.2f}–${entry_low:.2f} with volume"
        elif price_vs_ma20 < -5:
            entry_low, entry_high = current * 0.98, current * 1.01
            setup = "support"
            alert = f"Enter here ${entry_low:.2f}–${entry_high:.2f}; stop on close below ${current * 0.92:.2f}"
        else:
            entry_low, entry_high = current * 0.97, current * 1.01
            setup = "trend"
            alert = f"Buy ${entry_low:.2f}–${entry_high:.2f} on next pullback day with above-avg volume"

        entry_mid = (entry_low + entry_high) / 2
        volatility = ytd_range / low_52w if low_52w > 0 else 0.3
        stop_pct = max(0.08, min(0.18, volatility * 0.25))
        stop = entry_mid * (1 - stop_pct)
        t1 = entry_mid * 1.175
        t2 = entry_mid * 1.35
        risk = entry_mid - stop
        rr = (t1 - entry_mid) / risk if risk > 0 else 0

        position_size = "4-5%" if score >= 4 else "3-4%" if score >= 2 else "1-2%"

        name = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector", "")
        thesis = build_thesis(ticker, name, signal, rsi, range_pct, price_vs_ma50, vol_ratio, setup, sector)

        start_of_year = closes[-252] if len(closes) >= 252 else closes[0]
        ytd_return = (current - start_of_year) / start_of_year * 100 if start_of_year > 0 else 0

        result = {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "price": round(current, 2),
            "ytd": round(ytd_return, 1),
            "rsi": rsi,
            "signal": signal,
            "signal_class": signal_class,
            "score": score,
            "factors": ", ".join(factors[:4]),
            "entry_low": round(entry_low, 2),
            "entry_high": round(entry_high, 2),
            "stop": round(stop, 2),
            "t1": round(t1, 2),
            "t2": round(t2, 2),
            "rr": round(rr, 2),
            "position_size": position_size,
            "alert": alert,
            "thesis": thesis,
            "is_etf": ticker in ETF_SET,
            "div_yield": None,
            "mer": None,
            "aum": None,
        }

        if ticker in ETF_SET:
            result["div_yield"] = round((info.get("dividendYield") or 0) * 100, 2)
            result["mer"] = round(info.get("annualReportExpenseRatio") or 0, 4)
            result["aum"] = info.get("totalAssets") or 0

        return result

    except Exception as e:
        print(f"  Score error {ticker}: {e}")
        return None


def build_thesis(ticker, name, signal, rsi, range_pct, vs_ma50, vol_ratio, setup, sector):
    parts = []
    if signal in ("Strong Buy", "Buy"):
        if setup == "pullback":
            parts.append(
                f"{name} is extended short-term after a strong run but the underlying trend remains intact."
            )
            parts.append("Waiting for a healthy pullback to support before entering reduces risk significantly.")
        elif setup == "support":
            parts.append(
                f"{name} has pulled back to a technical support level, offering an asymmetric entry point."
            )
            parts.append("Risk is well-defined against recent lows.")
        else:
            parts.append(
                f"{name} is trending above its 50-day moving average with constructive price action."
            )
            if vol_ratio > 1.2:
                parts.append("Above-average volume confirms institutional participation.")
    elif signal == "Hold":
        parts.append(f"{name} is in a neutral zone — no clear edge in either direction right now.")
        parts.append("Hold existing positions; no new entries until a cleaner setup develops.")
    else:
        parts.append(f"{name} shows weakening momentum. RSI and trend indicators are deteriorating.")
        parts.append("Reduce exposure or avoid new positions until conditions improve.")

    if rsi < 35:
        parts.append(f"RSI at {rsi:.0f} indicates oversold conditions — short-term bounce likely.")
    elif rsi > 72:
        parts.append(f"RSI at {rsi:.0f} is elevated; avoid chasing.")

    if range_pct < 0.25:
        parts.append("Price is near the 52-week low, creating a potential base-building opportunity.")
    elif range_pct > 0.90:
        parts.append("Trading near 52-week highs. Breakout plays require high conviction and tight stops.")

    if sector:
        parts.append(f"Sector: {sector}.")

    return " ".join(parts)


# ─── HTML TEMPLATE ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Scanner</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #f4efe6; color: #2c2419; font-family: 'IBM Plex Mono', monospace; font-size: 13px; line-height: 1.5; }
header { background: #faf7f1; border-bottom: 1px solid #d4c9b8; padding: 20px 32px; display: flex; justify-content: space-between; align-items: center; }
.logo { font-family: 'EB Garamond', serif; font-size: 22px; font-weight: 600; color: #1a1008; letter-spacing: 0.01em; }
.logo span { color: #8a7560; font-weight: 400; font-size: 14px; margin-left: 12px; }
.updated { color: #8a7560; font-size: 11px; }
.controls { background: #faf7f1; border-bottom: 1px solid #d4c9b8; padding: 12px 32px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.controls input, .controls select { background: #fff; border: 1px solid #d4c9b8; color: #2c2419; font-family: 'IBM Plex Mono', monospace; font-size: 12px; padding: 6px 10px; border-radius: 4px; outline: none; }
.controls input:focus, .controls select:focus { border-color: #8a7560; }
.controls input { width: 180px; }
.controls label { color: #5c4a35; font-size: 11px; margin-right: -6px; }
.stats { margin-left: auto; color: #8a7560; font-size: 11px; }
table { width: 100%; border-collapse: collapse; }
th { background: #ede8de; color: #5c4a35; font-family: 'EB Garamond', serif; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; padding: 8px 12px; text-align: left; border-bottom: 1px solid #d4c9b8; cursor: pointer; user-select: none; white-space: nowrap; }
th:hover { background: #e4ddd3; }
td { padding: 7px 12px; border-bottom: 1px solid #eae4da; vertical-align: top; }
tr.stock-row { cursor: pointer; transition: background 0.12s; }
tr.stock-row:hover { background: #ede8de; }
tr.stock-row.expanded { background: #e8e2d8; }
tr.detail-row td { background: #f0ebe0; border-bottom: 2px solid #d4c9b8; padding: 0; cursor: default; }
.detail-panel { padding: 20px 24px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.detail-block h4 { font-family: 'EB Garamond', serif; font-size: 13px; font-weight: 600; color: #5c4a35; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.06em; }
.detail-block p, .detail-block span { font-size: 12px; color: #2c2419; line-height: 1.6; }
.detail-block .mono { font-family: 'IBM Plex Mono', monospace; font-size: 13px; font-weight: 500; }
.detail-block .muted { color: #8a7560; font-size: 11px; }
.thesis-block { grid-column: 1 / -1; border-top: 1px solid #d4c9b8; padding-top: 14px; margin-top: 4px; }
.alert-block { grid-column: 1 / -1; background: #faf7f1; border: 1px solid #d4c9b8; border-radius: 4px; padding: 10px 14px; font-size: 12px; color: #1a1008; }
.alert-block strong { color: #5c4a35; }
.ticker-cell { font-family: 'IBM Plex Mono', monospace; font-size: 13px; font-weight: 500; color: #1a1008; min-width: 90px; }
.name-cell { font-family: 'EB Garamond', serif; font-size: 12px; font-weight: 500; color: #2c2419; min-width: 180px; max-width: 180px; }
.price-cell { font-family: 'IBM Plex Mono', monospace; text-align: right; color: #1a1008; }
.ytd-cell { font-family: 'IBM Plex Mono', monospace; text-align: right; }
.ytd-pos { color: #2d5a27; }
.ytd-neg { color: #7a2020; }
.rsi-cell { font-family: 'IBM Plex Mono', monospace; text-align: right; color: #5c4a35; }
.factors-cell { font-size: 11px; font-weight: 500; color: #5c4a35; min-width: 150px; max-width: 150px; }
.signal-badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 500; white-space: nowrap; }
.strong-buy { background: #d4edda; color: #1a4a1a; border: 1px solid #b8d9c0; }
.buy { background: #ddefd6; color: #2d5a27; border: 1px solid #c4ddb8; }
.hold { background: #f5edcc; color: #6b5400; border: 1px solid #e8d98a; }
.caution { background: #f5ddd8; color: #7a2020; border: 1px solid #e8c4bc; }
.div-cell, .mer-cell, .aum-cell { font-family: 'IBM Plex Mono', monospace; font-size: 11px; text-align: right; color: #5c4a35; }
.stars { color: #c4a020; letter-spacing: 1px; }
.rr-good { color: #2d5a27; }
.rr-ok { color: #5c4a35; }
.rr-bad { color: #7a2020; }
.section-header td { background: #ede8de; font-family: 'EB Garamond', serif; font-size: 13px; font-weight: 600; color: #5c4a35; padding: 10px 12px 6px; letter-spacing: 0.04em; border-top: 2px solid #d4c9b8; cursor: default; }
.disclaimer { padding: 20px 32px; color: #8a7560; font-size: 10px; border-top: 1px solid #d4c9b8; line-height: 1.6; }
</style>
</head>
<body>
<header>
  <div class="logo">Market Scanner <span>Automated US + CA signals</span></div>
  <div class="updated">Updated: {updated}</div>
</header>
<div class="controls">
  <label>Search:</label>
  <input type="text" id="searchInput" placeholder="Ticker or name...">
  <label>Signal:</label>
  <select id="signalFilter">
    <option value="">All signals</option>
    <option value="strong-buy">Strong Buy</option>
    <option value="buy">Buy</option>
    <option value="hold">Hold</option>
    <option value="caution">Caution</option>
  </select>
  <label>Type:</label>
  <select id="typeFilter">
    <option value="">All types</option>
    <option value="stock">Stocks only</option>
    <option value="etf">ETFs only</option>
  </select>
  <label>Market:</label>
  <select id="marketFilter">
    <option value="">US + CA</option>
    <option value="us">US only</option>
    <option value="ca">Canada only</option>
  </select>
  <div class="stats" id="stats"></div>
</div>
<table id="mainTable">
<thead><tr>
  <th data-key="ticker">Ticker</th>
  <th data-key="name">Name</th>
  <th data-key="price" style="text-align:right">Price</th>
  <th data-key="ytd" style="text-align:right">YTD %</th>
  <th data-key="rsi" style="text-align:right">RSI</th>
  <th data-key="signal">Signal</th>
  <th>Factors</th>
  <th data-key="rr" style="text-align:right">R:R</th>
  <th style="text-align:right">Div%</th>
  <th style="text-align:right">MER</th>
  <th style="text-align:right">AUM</th>
</tr></thead>
<tbody id="tableBody"></tbody>
</table>
<div class="disclaimer">
  Not financial advice. All signals are algorithmic estimates based on price action and publicly available data.
  Entry zones, stop losses, and targets are starting points for your own analysis.
  Always do your own due diligence before trading. Data sourced from Yahoo Finance via yfinance.
</div>
<script>
const allData = {data_json};
let sortKey = 'score', sortDir = -1, expandedRow = null;

function formatAUM(v) {
  if (!v) return '—';
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(0) + 'M';
  return '$' + v;
}
function rrClass(rr) { return rr >= 2 ? 'rr-good' : rr >= 1 ? 'rr-ok' : 'rr-bad'; }
function starRating(score) {
  const s = Math.round(Math.max(1, Math.min(5, (score + 4) / 2)));
  return '<span class="stars">' + '★'.repeat(s) + '☆'.repeat(5 - s) + '</span>';
}

function renderTable(data) {
  const tbody = document.getElementById('tableBody');
  let html = '', lastSection = '';
  data.forEach((d, idx) => {
    const section = d.is_etf
      ? (d.ticker.endsWith('.TO') ? 'Canadian ETFs' : 'US ETFs')
      : (d.ticker.endsWith('.TO') ? 'Canadian Stocks' : 'US Stocks');
    if (section !== lastSection) {
      html += `<tr class="section-header"><td colspan="11">${section}</td></tr>`;
      lastSection = section;
    }
    const ytdSign = d.ytd >= 0 ? '+' : '';
    const ytdClass = d.ytd >= 0 ? 'ytd-pos' : 'ytd-neg';
    const div = d.div_yield != null ? d.div_yield.toFixed(2) + '%' : '—';
    const mer = d.mer ? (d.mer * 100).toFixed(2) + '%' : '—';
    const aum = formatAUM(d.aum);
    html += `<tr class="stock-row" id="row-${idx}" onclick="toggleDetail(${idx})">
      <td class="ticker-cell">${d.ticker}</td>
      <td class="name-cell">${d.name}</td>
      <td class="price-cell">$${d.price.toFixed(2)}</td>
      <td class="ytd-cell ${ytdClass}">${ytdSign}${d.ytd.toFixed(1)}%</td>
      <td class="rsi-cell">${d.rsi}</td>
      <td><span class="signal-badge ${d.signal_class}">${d.signal}</span></td>
      <td class="factors-cell">${d.factors}</td>
      <td class="${rrClass(d.rr)}" style="text-align:right;font-family:'IBM Plex Mono',monospace">${d.rr.toFixed(1)}:1</td>
      <td class="div-cell">${div}</td>
      <td class="mer-cell">${mer}</td>
      <td class="aum-cell">${d.is_etf ? aum : '—'}</td>
    </tr>
    <tr class="detail-row" id="detail-${idx}" style="display:none"><td colspan="11">
      <div class="detail-panel">
        <div class="detail-block">
          <h4>Entry Zone</h4>
          <div class="mono">$${d.entry_low.toFixed(2)} — $${d.entry_high.toFixed(2)}</div>
          <div class="muted">Buy between these levels</div>
        </div>
        <div class="detail-block">
          <h4>Stop Loss</h4>
          <div class="mono" style="color:#7a2020">$${d.stop.toFixed(2)}</div>
          <div class="muted">Exit if thesis breaks</div>
        </div>
        <div class="detail-block">
          <h4>Targets</h4>
          <div class="mono">T1: $${d.t1.toFixed(2)} <span class="muted">(scale out 50%)</span></div>
          <div class="mono">T2: $${d.t2.toFixed(2)} <span class="muted">(trail stop)</span></div>
        </div>
        <div class="detail-block">
          <h4>Risk / Reward</h4>
          <div class="mono ${rrClass(d.rr)}">${d.rr.toFixed(2)}:1</div>
          <div class="muted">Position size: ${d.position_size} of portfolio</div>
        </div>
        <div class="detail-block">
          <h4>RSI</h4>
          <div class="mono">${d.rsi}</div>
          <div class="muted">${d.rsi < 35 ? 'Oversold zone' : d.rsi > 70 ? 'Overbought zone' : 'Neutral range'}</div>
        </div>
        <div class="detail-block">
          <h4>YTD Return</h4>
          <div class="mono ${d.ytd >= 0 ? 'ytd-pos' : 'ytd-neg'}">${d.ytd >= 0 ? '+' : ''}${d.ytd.toFixed(1)}%</div>
          ${d.is_etf && d.div_yield ? `<div class="muted">Div: ${d.div_yield.toFixed(2)}%</div>` : ''}
        </div>
        <div class="alert-block"><strong>Alert Trigger:</strong> ${d.alert}</div>
        <div class="thesis-block">
          <h4 style="font-family:'EB Garamond',serif;font-size:13px;font-weight:600;color:#5c4a35;margin-bottom:6px;text-transform:uppercase;letter-spacing:.06em">Thesis</h4>
          <p style="font-size:12px;line-height:1.7;color:#2c2419">${d.thesis}</p>
        </div>
      </div>
    </td></tr>`;
  });
  tbody.innerHTML = html;
  document.getElementById('stats').textContent = data.length + ' instruments';
}

function toggleDetail(idx) {
  const dr = document.getElementById('detail-' + idx);
  const sr = document.getElementById('row-' + idx);
  if (expandedRow === idx) {
    dr.style.display = 'none';
    sr.classList.remove('expanded');
    expandedRow = null;
  } else {
    if (expandedRow !== null) {
      document.getElementById('detail-' + expandedRow).style.display = 'none';
      document.getElementById('row-' + expandedRow).classList.remove('expanded');
    }
    dr.style.display = 'table-row';
    sr.classList.add('expanded');
    expandedRow = idx;
  }
}

function filterAndRender() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  const signal = document.getElementById('signalFilter').value;
  const type = document.getElementById('typeFilter').value;
  const market = document.getElementById('marketFilter').value;
  expandedRow = null;
  let filtered = allData.filter(d => {
    return (!search || d.ticker.toLowerCase().includes(search) || d.name.toLowerCase().includes(search))
      && (!signal || d.signal_class === signal)
      && (!type || (type === 'etf' ? d.is_etf : !d.is_etf))
      && (!market || (market === 'ca' ? d.ticker.endsWith('.TO') : !d.ticker.endsWith('.TO')));
  });
  filtered = [...filtered].sort((a, b) => {
    const av = a[sortKey] ?? 0, bv = b[sortKey] ?? 0;
    return typeof av === 'string' ? sortDir * av.localeCompare(bv) : sortDir * (av - bv);
  });
  renderTable(filtered);
}

document.querySelectorAll('th[data-key]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.key;
    sortDir = (sortKey === key) ? sortDir * -1 : -1;
    sortKey = key;
    filterAndRender();
  });
});
document.getElementById('searchInput').addEventListener('input', filterAndRender);
document.getElementById('signalFilter').addEventListener('change', filterAndRender);
document.getElementById('typeFilter').addEventListener('change', filterAndRender);
document.getElementById('marketFilter').addEventListener('change', filterAndRender);

filterAndRender();
</script>
</body>
</html>"""


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_scan():
    all_tickers_ordered = US_STOCKS + US_ETFS + CA_STOCKS + CA_ETFS
    seen, tickers = set(), []
    for t in all_tickers_ordered:
        if t not in seen:
            seen.add(t)
            tickers.append(t)

    print(f"Scanning {len(tickers)} tickers...")
    results = []
    BATCH = 50

    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        print(f"  Batch {i // BATCH + 1}/{(len(tickers) + BATCH - 1) // BATCH}: {batch[0]}..{batch[-1]}")
        try:
            data = yf.download(
                " ".join(batch),
                period="1y",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as e:
            print(f"  Download error: {e}")
            continue

        for ticker in batch:
            try:
                hist = data[ticker] if len(batch) > 1 and ticker in data.columns.get_level_values(0) else (data if len(batch) == 1 else None)
                if hist is None or hist.empty:
                    continue
                info = {}
                try:
                    info = yf.Ticker(ticker).info
                    time.sleep(0.15)
                except Exception:
                    pass
                r = score_ticker(ticker, info, hist)
                if r:
                    results.append(r)
            except Exception as e:
                print(f"  Error {ticker}: {e}")

    print(f"Scored {len(results)} tickers. Writing dashboard...")
    signal_order = {"Strong Buy": 0, "Buy": 1, "Hold": 2, "Caution": 3}
    results.sort(key=lambda x: (-x["score"], signal_order.get(x["signal"], 4), x["ticker"]))

    updated = datetime.now().strftime("%B %d, %Y at %H:%M ET")
    html = HTML_TEMPLATE.replace("{updated}", updated).replace("{data_json}", json.dumps(results, ensure_ascii=False))

    out = Path("docs")
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard written to docs/index.html")


if __name__ == "__main__":
    run_scan()
