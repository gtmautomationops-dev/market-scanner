#!/usr/bin/env python3
"""
Market Scanner — Technical + Volume + Peter Lynch composite scoring.
Outputs docs/index.html for GitHub Pages deployment.
Also writes docs/email_alert.html for GitHub Actions email delivery.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

# ─── TICKER LISTS ─────────────────────────────────────────────────────────────

US_STOCKS = [
    "AAPL", "MSFT", "NVDA", "AMD", "INTC", "QCOM", "AVGO", "MU", "AMAT",
    "LRCX", "KLAC", "ASML", "ARM", "SMCI", "PLTR", "SNOW", "CRM", "NOW", "ORCL",
    "META", "GOOGL", "AMZN", "NFLX", "UBER", "ABNB", "SHOP", "SQ", "PYPL",
    "COIN", "MSTR", "HOOD", "RBLX", "TTD", "ZS", "CRWD", "PANW", "OKTA",
    "NET", "DDOG", "MDB", "CFLT", "GTLB",
    "XOM", "CVX", "COP", "EOG", "DVN", "HAL", "SLB", "BKR", "MPC",
    "PSX", "VLO", "OXY", "APA", "FANG", "CTRA", "EQT", "AR", "RRC",
    "JPM", "BAC", "WFC", "GS", "MS", "C", "USB", "PNC", "TFC", "COF",
    "AXP", "V", "MA", "BRK-B", "BLK", "SCHW", "ICE", "CME", "SPGI", "MCO",
    "JNJ", "PFE", "ABBV", "MRK", "LLY", "BMY", "AMGN", "GILD", "REGN", "VRTX",
    "ISRG", "MDT", "EW", "BDX", "DHR", "TMO", "IQV",
    "GEV", "GE", "RTX", "LMT", "NOC", "BA", "HON", "CAT", "DE", "EMR",
    "ETN", "PH", "ROK", "AME", "FTV", "XYL", "TT",
    "WMT", "TGT", "COST", "HD", "LOW", "TJX", "ROST", "NKE", "LULU",
    "MCD", "SBUX", "YUM", "CMG", "DPZ", "DRI",
    "AMT", "PLD", "CCI", "EQIX", "PSA", "EXR", "AVB", "EQR",
    "NEM", "FCX", "GOLD", "AA", "NUE", "RS",
    "NEE", "SO", "DUK", "AEP", "D", "EXC", "XEL", "WEC", "AWK",
    # AI / next-gen tech
    "AI", "IONQ", "RGTI", "QBTS", "BBAI", "SOUN", "IREN", "CORZ", "APLD",
    "NBIS", "LITE", "AAOI", "SIVEF", "AXTI", "AEHR", "FLNC", "ABB",
    "SOFI", "RDDT", "OPEN",
    # AI power infrastructure
    "VRT", "VST", "CEG", "TLN", "DLR", "IRM", "WMB", "ET",
    # Memory
    "DRAM",
]

US_ETFS = [
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VEA", "VWO",
    "AGG", "BND", "TLT", "IEF", "SHY", "HYG", "JNK", "LQD", "EMB",
    "XLK", "XLE", "XLF", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    "SMH", "SOXX", "ARKK", "ARKG", "ARKF",
    "SCHD", "VYM", "DVY", "HDV", "NOBL", "VIG", "SDY", "DGRO",
    "GLD", "SLV", "USO", "UNG", "PDBC",
    "EFA", "EEM", "FXI", "EWJ", "EWZ", "KWEB",
    "TQQQ", "SOXL", "UPRO",
    "AIPO",
]

CA_STOCKS = [
    "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "NA.TO", "EQB.TO",
    "CNQ.TO", "SU.TO", "CVE.TO", "ATH.TO", "MEG.TO", "BTE.TO", "ARX.TO",
    "TOU.TO", "WCP.TO", "BIR.TO", "ERF.TO", "CPG.TO",
    "ABX.TO", "AEM.TO", "WPM.TO", "KL.TO", "FNV.TO", "IMG.TO", "MAG.TO",
    "SHOP.TO", "CSU.TO", "TOI.TO", "LSPD.TO", "DCBO.TO",
    "CNR.TO", "CP.TO", "WSP.TO", "STN.TO", "BYD.TO", "TIH.TO",
    "BCE.TO", "T.TO", "RCI-B.TO", "FTS.TO", "H.TO", "BEP-UN.TO",
    "ATD.TO", "L.TO", "MRU.TO", "DOL.TO", "CTC-A.TO", "EMP-A.TO",
    "CAR-UN.TO", "REI-UN.TO", "AP-UN.TO", "HR-UN.TO",
    "MFC.TO", "SLF.TO", "GWO.TO", "FFH.TO", "POW.TO",
]

CA_ETFS = [
    "XIU.TO", "XIC.TO", "ZCN.TO", "VCN.TO", "HXT.TO",
    "XDV.TO", "CDZ.TO", "VDY.TO", "ZWB.TO",
    "XEG.TO", "XFN.TO", "XGD.TO", "ZEB.TO",
    "XSP.TO", "ZSP.TO", "VSP.TO", "XQQ.TO", "ZQQ.TO",
    "XBB.TO", "ZAG.TO", "VAB.TO", "XSB.TO",
    "XEF.TO", "ZEA.TO", "VEE.TO",
    "XGRO.TO", "XBAL.TO", "VGRO.TO", "VBAL.TO", "VCNS.TO",
    "XEQT.TO", "VEQT.TO", "ZEQT.TO",
]

ETF_SET = set(US_ETFS + CA_ETFS)

BOND_ETF_SET = {
    "AGG", "BND", "TLT", "IEF", "SHY", "HYG", "JNK", "LQD", "EMB",
    "XBB.TO", "ZAG.TO", "VAB.TO", "XSB.TO",
}

CYCLICAL_SECTORS = {"Energy", "Basic Materials", "Consumer Cyclical", "Industrials", "Financial Services"}
DEFENSIVE_SECTORS = {"Consumer Defensive", "Healthcare", "Utilities", "Real Estate"}


# ─── TECHNICAL INDICATORS ─────────────────────────────────────────────────────

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


def calculate_obv(closes, volumes):
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


# ─── VOLUME SCORING ───────────────────────────────────────────────────────────

def score_volume(hist):
    """
    Returns (score -3..+3, signal_label, details_dict).
    Checks: OBV trend, volume surge, price-volume confirmation, pullback volume.
    """
    score = 0
    details = {}

    if hist is None or len(hist) < 20:
        return 0, "Insufficient data", details

    closes = list(hist["Close"].dropna())
    if "Volume" not in hist.columns or len(closes) < 20:
        return 0, "No volume data", details

    volumes = list(hist["Volume"].fillna(0))
    if len(volumes) != len(closes):
        return 0, "Data mismatch", details

    # --- OBV trend ---
    obv = calculate_obv(closes, volumes)
    obv_5d = sum(obv[-5:]) / 5 if len(obv) >= 5 else obv[-1]
    obv_20d = sum(obv[-20:]) / 20 if len(obv) >= 20 else obv_5d
    obv_50d = sum(obv[-50:]) / 50 if len(obv) >= 50 else obv_20d

    if obv_5d > obv_20d > obv_50d:
        score += 2
        details["obv"] = "Accumulating (OBV rising)"
    elif obv_5d > obv_20d:
        score += 1
        details["obv"] = "Mild accumulation"
    elif obv_5d < obv_20d < obv_50d:
        score -= 2
        details["obv"] = "Distributing (OBV falling)"
    elif obv_5d < obv_20d:
        score -= 1
        details["obv"] = "Mild distribution"
    else:
        details["obv"] = "Neutral OBV"

    # --- Volume surge (last 5d vs 20d avg) ---
    vol_5d = sum(volumes[-5:]) / 5
    vol_20d = sum(volumes[-20:]) / 20
    vol_ratio = vol_5d / vol_20d if vol_20d > 0 else 1.0
    details["vol_ratio"] = round(vol_ratio, 2)

    if vol_ratio >= 2.0:
        score += 2
        details["surge"] = f"Volume surge {vol_ratio:.1f}x avg (institutional activity)"
    elif vol_ratio >= 1.4:
        score += 1
        details["surge"] = f"Above-avg volume {vol_ratio:.1f}x"
    elif vol_ratio <= 0.5:
        score -= 1
        details["surge"] = f"Low volume {vol_ratio:.1f}x — weak conviction"
    else:
        details["surge"] = f"Normal volume {vol_ratio:.1f}x"

    # --- Price-volume confirmation (last 5 days) ---
    if len(closes) >= 6:
        price_up = closes[-1] > closes[-6]
        vol_confirming = vol_5d > vol_20d
        if price_up and vol_confirming:
            score += 1
            details["pv_confirm"] = "Price + volume both rising — bullish confirmation"
        elif not price_up and not vol_confirming:
            details["pv_confirm"] = "Price + volume both falling — distribution"
        elif price_up and not vol_confirming:
            details["pv_confirm"] = "Price up on low volume — weak breakout"
        else:
            score -= 1
            details["pv_confirm"] = "Price down on high volume — selling pressure"

    # --- Pullback volume (healthy pullback = low volume) ---
    if len(closes) >= 10:
        recent_pullback = closes[-1] < closes[-5]
        pullback_vol = sum(volumes[-3:]) / 3
        avg_vol = vol_20d
        if recent_pullback and pullback_vol < avg_vol * 0.7:
            score += 1
            details["pullback"] = "Pullback on low volume — healthy, buyers likely absorbing"
        elif recent_pullback and pullback_vol > avg_vol * 1.3:
            score -= 1
            details["pullback"] = "Pullback on high volume — sellers in control"

    label = (
        "Strong Accumulation" if score >= 3 else
        "Accumulation" if score >= 1 else
        "Distribution" if score <= -2 else
        "Mild Distribution" if score <= -1 else
        "Neutral"
    )
    return max(-3, min(3, score)), label, details


# ─── PETER LYNCH FRAMEWORK ────────────────────────────────────────────────────

def classify_lynch(info, hist_closes):
    """
    Classify a stock into Lynch's six categories and score it.
    Returns (category, score -3..+3, details_dict).
    """
    details = {}
    score = 0

    eps_growth = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
    rev_growth = info.get("revenueGrowth") or info.get("revenueQuarterlyGrowth")
    peg = info.get("pegRatio")
    pe = info.get("trailingPE") or info.get("forwardPE")
    roe = info.get("returnOnEquity")
    debt_eq = info.get("debtToEquity")
    profit_margin = info.get("profitMargins")
    div_yield = info.get("dividendYield") or 0
    sector = info.get("sector", "")
    market_cap = info.get("marketCap") or 0
    fcf = info.get("freeCashflow")
    total_cash = info.get("totalCash") or 0
    total_debt = info.get("totalDebt") or 0

    details["eps_growth"] = round((eps_growth or 0) * 100, 1)
    details["rev_growth"] = round((rev_growth or 0) * 100, 1)
    details["peg"] = round(peg, 2) if peg else None
    details["pe"] = round(pe, 1) if pe else None
    details["roe"] = round((roe or 0) * 100, 1)
    details["debt_eq"] = round(debt_eq / 100, 2) if debt_eq else None
    details["profit_margin"] = round((profit_margin or 0) * 100, 1)
    details["div_yield"] = round(div_yield * 100, 2)

    trailing_eps = info.get("trailingEps")
    is_loss_making = (
        (trailing_eps is not None and trailing_eps < 0) or
        (pe is None and roe is not None and roe < -0.05) or
        (profit_margin is not None and profit_margin < -0.05)
    )

    eg = (eps_growth or 0) * 100  # as percentage
    # If company is clearly losing money but yfinance returns no growth data, force negative
    if is_loss_making and eps_growth is None:
        eg = -1.0

    # --- Classify ---
    if eg > 20 and (debt_eq is None or debt_eq < 100):
        category = "Fast Grower"
        details["category_desc"] = "Lynch's favourite: high-growth, manageable debt. Look for PEG < 1."
    elif 10 <= eg <= 20:
        category = "Stalwart"
        details["category_desc"] = "Large, stable company. Lynch holds for 30-50% gain then moves on."
    elif eg > 0 and sector in CYCLICAL_SECTORS:
        category = "Cyclical"
        details["category_desc"] = "Profits tied to economic cycle. Buy near cycle trough, sell near peak."
    elif eg < 0:
        category = "Turnaround"
        details["category_desc"] = "Currently struggling. Lynch looks for catalyst and improving cash flow."
    elif total_cash > market_cap * 0.3 and market_cap > 0:
        category = "Asset Play"
        details["category_desc"] = "Assets worth more than market price. Lynch hunts hidden balance sheet value."
    elif div_yield > 0.02 or eg < 10:
        category = "Slow Grower"
        details["category_desc"] = "Low/flat growth. Lynch holds only for yield or if deeply undervalued."
    else:
        category = "Slow Grower"
        details["category_desc"] = "Low/flat growth. Not a Lynch pick unless PEG is very cheap."

    # --- PEG scoring (Lynch's primary metric) ---
    if peg is not None and peg > 0:
        if peg < 0.5:
            score += 3
            details["peg_signal"] = f"PEG {peg:.2f} — exceptional value (Lynch strong buy)"
        elif peg < 1.0:
            score += 2
            details["peg_signal"] = f"PEG {peg:.2f} — good value (Lynch buy zone)"
        elif peg < 1.5:
            score += 1
            details["peg_signal"] = f"PEG {peg:.2f} — fair value"
        elif peg < 2.0:
            score -= 1
            details["peg_signal"] = f"PEG {peg:.2f} — slightly rich"
        else:
            score -= 2
            details["peg_signal"] = f"PEG {peg:.2f} — overvalued (Lynch avoid)"
    elif pe and pe > 0:
        # No PEG: use P/E as fallback
        if pe < 15:
            score += 1
            details["peg_signal"] = f"P/E {pe:.1f} — cheap (no PEG available)"
        elif pe > 40:
            score -= 1
            details["peg_signal"] = f"P/E {pe:.1f} — expensive (no PEG available)"
        else:
            details["peg_signal"] = f"P/E {pe:.1f} — moderate"
    else:
        details["peg_signal"] = "No P/E data"

    # --- Earnings growth ---
    if eg > 25:
        score += 1
        details["growth_signal"] = f"EPS growth {eg:.1f}% — strong"
    elif eg > 10:
        details["growth_signal"] = f"EPS growth {eg:.1f}% — healthy"
    elif eg < 0:
        score -= 1
        details["growth_signal"] = f"EPS growth {eg:.1f}% — negative"
    else:
        details["growth_signal"] = f"EPS growth {eg:.1f}%"

    # --- Debt check (Lynch dislikes heavy debt) ---
    if debt_eq is not None:
        debt_ratio = debt_eq / 100
        if debt_ratio < 0.3:
            score += 1
            details["debt_signal"] = f"Debt/Equity {debt_ratio:.2f} — low debt (Lynch approves)"
        elif debt_ratio > 1.5:
            score -= 1
            details["debt_signal"] = f"Debt/Equity {debt_ratio:.2f} — high debt (Lynch caution)"
        else:
            details["debt_signal"] = f"Debt/Equity {debt_ratio:.2f} — manageable"
    else:
        details["debt_signal"] = "Debt data unavailable"

    # --- ROE ---
    if roe:
        roe_pct = roe * 100
        if roe_pct > 20:
            score += 1
            details["roe_signal"] = f"ROE {roe_pct:.1f}% — excellent"
        elif roe_pct > 10:
            details["roe_signal"] = f"ROE {roe_pct:.1f}% — solid"
        else:
            details["roe_signal"] = f"ROE {roe_pct:.1f}% — weak"
    else:
        details["roe_signal"] = "ROE unavailable"

    # --- Free cash flow ---
    if fcf and fcf > 0:
        score += 1
        details["fcf_signal"] = "Positive free cash flow — self-funding business"
    elif fcf and fcf < 0:
        score -= 1
        details["fcf_signal"] = "Negative free cash flow — burning cash"
    else:
        details["fcf_signal"] = "FCF data unavailable"

    return category, max(-5, min(5, score)), details


# ─── ENTRY / EXIT LOGIC ───────────────────────────────────────────────────────

def compute_atr(closes, period=14):
    if len(closes) < period + 1:
        return closes[-1] * 0.02
    true_ranges = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    return sum(true_ranges[-period:]) / period


def compute_entry_exit(current, closes, price_vs_ma20, range_pct, score):
    if range_pct > 0.85 or price_vs_ma20 > 12:
        entry_low = current * 0.85
        entry_high = current * 0.90
        setup = "pullback"
        alert = f"Wait for pullback to ${entry_high:.2f}–${entry_low:.2f} with volume"
    elif price_vs_ma20 < -5:
        entry_low = current * 0.98
        entry_high = current * 1.01
        setup = "support"
        alert = f"Enter at support ${entry_low:.2f}–${entry_high:.2f}; stop below ${current * 0.92:.2f}"
    else:
        entry_low = current * 0.97
        entry_high = current * 1.01
        setup = "trend"
        alert = f"Buy ${entry_low:.2f}–${entry_high:.2f} on next pullback with above-avg volume"

    entry_mid = (entry_low + entry_high) / 2

    # ATR-based stop: 2× ATR below entry, clamped 6–20% so it reflects real volatility
    atr = compute_atr(closes)
    atr_stop = (2 * atr) / entry_mid
    stop_pct = max(0.06, min(0.20, atr_stop))
    stop = entry_mid * (1 - stop_pct)

    # Targets: swing-high resistance as T1, 2× extension as T2
    recent = closes[-60:] if len(closes) >= 60 else closes
    swing_highs = sorted([h for h in recent if h > entry_mid * 1.05], )
    t1 = swing_highs[len(swing_highs) // 2] if swing_highs else entry_mid * (1 + stop_pct * 2.5)
    t2 = entry_mid + (t1 - entry_mid) * 2

    risk = entry_mid - stop
    rr = (t1 - entry_mid) / risk if risk > 0 else 0
    position_size = "4-5%" if score >= 6 else "3-4%" if score >= 3 else "1-2%"
    return entry_low, entry_high, entry_mid, stop, t1, t2, round(rr, 2), position_size, setup, alert


# ─── THESIS BUILDER ───────────────────────────────────────────────────────────

def build_thesis(name, signal, rsi, range_pct, vs_ma50, vol_ratio, setup,
                 sector, lynch_cat, lynch_details, vol_details):
    parts = []

    if signal in ("Strong Buy", "Buy"):
        if setup == "pullback":
            parts.append(f"{name} is extended short-term but the trend is intact.")
            parts.append("A pullback to support is the ideal entry to reduce risk.")
        elif setup == "support":
            parts.append(f"{name} has pulled back to a support zone — asymmetric entry.")
        else:
            parts.append(f"{name} is trending constructively above its 50-day moving average.")
    elif signal == "Hold":
        parts.append(f"{name} is in a neutral zone with no clear directional edge.")
    else:
        parts.append(f"{name} shows deteriorating momentum. Avoid new positions.")

    if lynch_cat:
        desc = lynch_details.get("category_desc", "")
        parts.append(f"Lynch classifies this as a {lynch_cat}. {desc}")

    peg_sig = lynch_details.get("peg_signal", "")
    if peg_sig:
        parts.append(peg_sig + ".")

    obv = vol_details.get("obv", "")
    if obv:
        parts.append(obv + ".")

    if rsi < 35:
        parts.append(f"RSI at {rsi:.0f} — oversold, bounce likely.")
    elif rsi > 72:
        parts.append(f"RSI at {rsi:.0f} — overbought, avoid chasing.")

    if range_pct < 0.25:
        parts.append("Near 52-week low — potential base building.")
    elif range_pct > 0.90:
        parts.append("Near 52-week high — breakout requires strong conviction.")

    return " ".join(parts)


# ─── MAIN SCORER ──────────────────────────────────────────────────────────────

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
        range_pct = (current - low_52w) / (high_52w - low_52w) if high_52w != low_52w else 0.5

        rsi = calculate_rsi(closes[-60:] if len(closes) >= 60 else closes)
        ma20 = sum(closes[-20:]) / 20
        ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sum(closes) / len(closes)
        price_vs_ma20 = (current - ma20) / ma20 * 100
        price_vs_ma50 = (current - ma50) / ma50 * 100

        # ── Technical score ──
        tech_score = 0
        tech_factors = []

        if price_vs_ma50 > 5:
            tech_score += 2; tech_factors.append("Above 50MA")
        elif price_vs_ma50 > 0:
            tech_score += 1; tech_factors.append("Near 50MA")
        else:
            tech_score -= 1; tech_factors.append("Below 50MA")

        if 40 <= rsi <= 65:
            tech_score += 2; tech_factors.append(f"RSI {rsi:.0f}")
        elif rsi < 30:
            tech_score += 1; tech_factors.append(f"RSI {rsi:.0f} oversold")
        elif rsi > 75:
            tech_score -= 2; tech_factors.append(f"RSI {rsi:.0f} overbought")
        else:
            tech_factors.append(f"RSI {rsi:.0f}")

        if range_pct < 0.35:
            tech_score += 2; tech_factors.append("Near 52W low")
        elif range_pct > 0.85:
            tech_score -= 1; tech_factors.append("Near 52W high")
        else:
            tech_score += 1

        if price_vs_ma20 > 10:
            tech_score -= 1; tech_factors.append("Extended")
        elif price_vs_ma20 < -5:
            tech_score += 1; tech_factors.append("Pullback")

        # ── Volume score ──
        vol_score, vol_label, vol_details = score_volume(hist)
        if vol_score >= 2:
            tech_factors.append(vol_label)
        elif vol_score <= -2:
            tech_factors.append(vol_label)

        # ── Lynch score (stocks only) ──
        is_etf = ticker in ETF_SET
        if not is_etf:
            lynch_cat, lynch_score, lynch_details = classify_lynch(info, closes)
        else:
            lynch_cat, lynch_score, lynch_details = "ETF", 0, {}

        # ── Composite score (weighted) ──
        # Technical 40%, Volume 20%, Lynch 40% (stocks) / Technical 60% Vol 40% (ETFs)
        if is_etf:
            composite = tech_score * 0.6 + vol_score * 0.4
        else:
            composite = tech_score * 0.4 + vol_score * 0.2 + lynch_score * 0.4

        entry_low, entry_high, entry_mid, stop, t1, t2, rr, position_size, setup, alert = (
            compute_entry_exit(current, closes, price_vs_ma20, range_pct, composite)
        )

        # Base signal from composite score
        if composite >= 3.0:
            signal, signal_class = "Strong Buy", "strong-buy"
        elif composite >= 1.0:
            signal, signal_class = "Buy", "buy"
        elif composite >= -0.5:
            signal, signal_class = "Hold", "hold"
        else:
            signal, signal_class = "Caution", "caution"

        # Cap signal based on R:R — strong fundamentals with a bad entry is still "wait"
        if rr < 1.0 and signal in ("Strong Buy", "Buy"):
            signal, signal_class = "Hold", "hold"
        elif rr < 2.0 and signal == "Strong Buy":
            signal, signal_class = "Buy", "buy"

        # Bond ETFs are income instruments — cap at Hold, not tradeable as buy signals
        if ticker in BOND_ETF_SET:
            if signal in ("Strong Buy", "Buy"):
                signal, signal_class = "Hold", "hold"

        name = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector", "")
        thesis = build_thesis(
            name, signal, rsi, range_pct, price_vs_ma50,
            vol_details.get("vol_ratio", 1.0), setup,
            sector, lynch_cat, lynch_details, vol_details
        )

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
            "composite": round(composite, 2),
            "tech_score": tech_score,
            "vol_score": vol_score,
            "lynch_score": lynch_score,
            "factors": ", ".join(tech_factors[:4]),
            "vol_label": vol_label,
            "lynch_cat": lynch_cat,
            "entry_low": round(entry_low, 2),
            "entry_high": round(entry_high, 2),
            "stop": round(stop, 2),
            "t1": round(t1, 2),
            "t2": round(t2, 2),
            "rr": rr,
            "position_size": position_size,
            "alert": alert,
            "thesis": thesis,
            "is_etf": is_etf,
            # Lynch detail fields
            "peg": lynch_details.get("peg"),
            "pe": lynch_details.get("pe"),
            "eps_growth": lynch_details.get("eps_growth"),
            "rev_growth": lynch_details.get("rev_growth"),
            "roe": lynch_details.get("roe"),
            "debt_eq": lynch_details.get("debt_eq"),
            "profit_margin": lynch_details.get("profit_margin"),
            "peg_signal": lynch_details.get("peg_signal", ""),
            "growth_signal": lynch_details.get("growth_signal", ""),
            "debt_signal": lynch_details.get("debt_signal", ""),
            "roe_signal": lynch_details.get("roe_signal", ""),
            "fcf_signal": lynch_details.get("fcf_signal", ""),
            "category_desc": lynch_details.get("category_desc", ""),
            # Volume detail fields
            "obv_signal": vol_details.get("obv", ""),
            "surge_signal": vol_details.get("surge", ""),
            "pv_confirm": vol_details.get("pv_confirm", ""),
            "pullback_signal": vol_details.get("pullback", ""),
            "vol_ratio": vol_details.get("vol_ratio", 1.0),
            # ETF fields
            "div_yield": None,
            "mer": None,
            "aum": None,
        }

        if is_etf:
            result["div_yield"] = round((info.get("dividendYield") or 0) * 100, 2)
            result["mer"] = round(info.get("annualReportExpenseRatio") or 0, 4)
            result["aum"] = info.get("totalAssets") or 0

        return result

    except Exception as e:
        print(f"  Score error {ticker}: {e}")
        return None


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
:root {
  --bg:#f4efe6; --surface:#faf7f1; --surface2:#ede8de; --border:#d4c9b8; --border2:#eae4da;
  --ink1:#1a1008; --ink2:#2c2419; --ink3:#5c4a35; --ink4:#8a7560;
  --green:#2d5a27; --green-dk:#1a4a1a; --green-bg:#d4edda; --green-bd:#b8d9c0;
  --gold:#6b5400; --gold-bg:#f5edcc;
  --red:#7a2020; --red-bg:#f5ddd8; --red-bd:#e8c4bc;
  --serif:'EB Garamond',Georgia,serif; --mono:'IBM Plex Mono','Courier New',monospace;
  --header-h:56px; --controls-h:44px;
}
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--ink2); font-family:var(--mono); font-size:13px; line-height:1.5; -webkit-text-size-adjust:100%; }
/* ── Layout ── */
header { background:var(--surface); border-bottom:1px solid var(--border); padding:0 20px; height:var(--header-h); display:flex; justify-content:space-between; align-items:center; position:sticky; top:0; z-index:100; box-shadow:0 1px 3px rgba(0,0,0,.07); }
.logo { font-family:var(--serif); font-size:20px; font-weight:600; color:var(--ink1); }
.logo small { font-size:13px; color:var(--ink4); font-weight:400; margin-left:10px; }
.updated { font-size:11px; color:var(--ink4); white-space:nowrap; }

.controls { background:var(--surface); border-bottom:2px solid var(--border); padding:0 20px; height:var(--controls-h); display:flex; gap:8px; align-items:center; position:sticky; top:var(--header-h); z-index:99; overflow-x:auto; }
.controls::-webkit-scrollbar { display:none; }
.controls input, .controls select { background:var(--bg); border:1px solid var(--border); color:var(--ink2); font-family:var(--mono); font-size:12px; padding:5px 9px; border-radius:4px; outline:none; height:30px; flex-shrink:0; }
.controls input { width:155px; }
.controls input:focus, .controls select:focus { border-color:var(--ink3); background:#fff; }
.controls label { font-size:11px; color:var(--ink3); flex-shrink:0; }
.stats { margin-left:auto; font-size:11px; color:var(--ink4); white-space:nowrap; padding-left:12px; flex-shrink:0; }

/* ── Badges ── */
.signal-badge { display:inline-block; padding:2px 8px; border-radius:3px; font-family:var(--mono); font-size:10px; font-weight:500; white-space:nowrap; }
.strong-buy { background:var(--green-bg); color:var(--green-dk); border:1px solid var(--green-bd); }
.buy { background:#ddefd6; color:var(--green); border:1px solid #c4ddb8; }
.hold { background:var(--gold-bg); color:var(--gold); border:1px solid #e8d98a; }
.caution { background:var(--red-bg); color:var(--red); border:1px solid var(--red-bd); }

/* ── Desktop table ── */
table { width:100%; border-collapse:collapse; }
thead th { background:var(--surface2); color:var(--ink3); font-family:var(--serif); font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.08em; padding:8px 12px; text-align:left; border-bottom:1px solid var(--border); cursor:pointer; user-select:none; white-space:nowrap; position:sticky; top:calc(var(--header-h) + var(--controls-h)); z-index:98; }
thead th:hover { background:#e4ddd3; }
thead th.asc::after { content:' ▲'; font-size:9px; }
thead th.desc::after { content:' ▼'; font-size:9px; }
td { padding:7px 12px; border-bottom:1px solid var(--border2); vertical-align:middle; }
tr.stock-row { cursor:pointer; transition:background .1s; }
tr.stock-row:hover { background:var(--surface2); }
tr.stock-row.expanded { background:#e8e2d8; }
tr.detail-row td { background:#ece6db; border-bottom:2px solid var(--border); padding:0; cursor:default; }
tr.section-header td { background:var(--surface2); font-family:var(--serif); font-size:13px; font-weight:600; color:var(--ink3); padding:9px 12px 5px; letter-spacing:.04em; border-top:2px solid var(--border); cursor:default; }

/* ── Cell types ── */
.tc { font-family:var(--mono); font-size:13px; font-weight:500; color:var(--ink1); min-width:80px; }
.nc { font-family:var(--serif); font-size:12px; font-weight:500; color:var(--ink2); min-width:150px; max-width:170px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mc { font-family:var(--mono); text-align:right; font-size:12px; color:var(--ink2); }
.ytd-pos { color:var(--green); }
.ytd-neg { color:var(--red); }
.rr-good { background:var(--green-bg); color:var(--green-dk); font-weight:700; border:1px solid var(--green-bd); }
.rr-ok   { background:#f0ece4;         color:var(--ink3);    font-weight:500; border:1px solid var(--border); }
.rr-bad  { background:var(--red-bg);   color:var(--red);     font-weight:700; border:1px solid var(--red-bd); }
.peg-good { color:var(--green); font-weight:500; }
.peg-fair { color:var(--gold); }
.peg-bad { color:var(--red); }
.fc { font-size:11px; color:var(--ink3); max-width:140px; }
.lc, .vc { font-size:11px; color:var(--ink3); white-space:nowrap; }

/* ── Detail panel ── */
.detail-panel { padding:16px 20px; }
.pillars { display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; margin-bottom:12px; }
.pillar { background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:12px 14px; }
.pillar h4 { font-family:var(--serif); font-size:12px; font-weight:600; color:var(--ink3); margin-bottom:8px; text-transform:uppercase; letter-spacing:.06em; display:flex; justify-content:space-between; align-items:center; }
.ps { font-family:var(--mono); font-size:11px; padding:1px 6px; border-radius:3px; }
.score-pos { background:var(--green-bg); color:var(--green-dk); }
.score-neg { background:var(--red-bg); color:var(--red); }
.score-neu { background:var(--gold-bg); color:var(--gold); }
.pr { font-size:11px; color:var(--ink3); margin-bottom:4px; line-height:1.5; }
.pr span { color:var(--ink2); font-weight:500; }
.entry-exit { display:grid; grid-template-columns:repeat(6,1fr); gap:10px; margin-bottom:12px; background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:12px 14px; }
.ee h4 { font-family:var(--serif); font-size:10px; font-weight:600; color:var(--ink4); text-transform:uppercase; letter-spacing:.06em; margin-bottom:3px; }
.ev { font-family:var(--mono); font-size:14px; font-weight:500; color:var(--ink1); }
.ev.sv { color:var(--red); }
.ev.tv { color:var(--green); }
.es { font-size:10px; color:var(--ink4); }
.alert-box { background:#fdf8ef; border:1px solid #e8d98a; border-radius:4px; padding:10px 12px; font-size:12px; color:var(--ink1); margin-bottom:10px; }
.alert-box strong { color:var(--gold); }
.thesis-box h4 { font-family:var(--serif); font-size:12px; font-weight:600; color:var(--ink3); margin-bottom:5px; text-transform:uppercase; letter-spacing:.06em; }
.thesis-box p { font-size:12px; line-height:1.7; color:var(--ink2); }

/* ── Mobile cards ── */
#mobile-list { display:none; padding:10px 12px 24px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:8px; margin-bottom:10px; overflow:hidden; }
.card-bar { height:4px; }
.card-bar.strong-buy { background:var(--green-dk); }
.card-bar.buy { background:var(--green); }
.card-bar.hold { background:var(--gold); }
.card-bar.caution { background:var(--red); }
.card-top { padding:12px 14px 6px; display:flex; justify-content:space-between; align-items:flex-start; cursor:pointer; }
.card-left .cticker { font-family:var(--mono); font-size:18px; font-weight:600; color:var(--ink1); }
.card-left .cname { font-family:var(--serif); font-size:12px; color:var(--ink3); margin-top:1px; }
.card-meta { padding:0 14px 10px; display:flex; gap:12px; flex-wrap:wrap; cursor:pointer; }
.cmeta { font-size:12px; color:var(--ink3); }
.cmeta strong { color:var(--ink1); }
.card-price { padding:8px 14px; background:var(--surface2); border-top:1px solid var(--border2); border-bottom:1px solid var(--border2); display:flex; justify-content:space-between; align-items:center; cursor:pointer; }
.cprice-label { font-size:10px; color:var(--ink4); text-transform:uppercase; letter-spacing:.05em; }
.cprice-val { font-family:var(--mono); font-size:22px; font-weight:600; color:var(--ink1); }
.cprice-hint { font-size:11px; color:var(--ink3); text-align:right; line-height:1.4; }
.card-levels { display:grid; grid-template-columns:repeat(4,1fr); padding:10px 14px; gap:8px; cursor:pointer; }
.cl h5 { font-size:10px; color:var(--ink4); text-transform:uppercase; letter-spacing:.04em; margin-bottom:2px; font-family:var(--serif); font-weight:600; }
.cl .clv { font-family:var(--mono); font-size:14px; font-weight:500; color:var(--ink1); }
.cl .clv.red { color:var(--red); }
.cl .clv.green { color:var(--green); }
.cl .cls { font-size:10px; color:var(--ink4); }
.card-alert { margin:0 14px 10px; background:#fdf8ef; border:1px solid #e8d98a; border-radius:4px; padding:8px 10px; font-size:12px; color:var(--ink2); line-height:1.5; }
.card-alert strong { color:var(--gold); }
.card-expand { border-top:1px solid var(--border); padding:12px 14px; display:none; }
.card.open .card-expand { display:block; }
.card-chevron { font-size:14px; color:var(--ink4); transition:transform .2s; margin-top:2px; }
.card.open .card-chevron { transform:rotate(180deg); }
.cpillar { margin-bottom:10px; }
.cpillar h4 { font-family:var(--serif); font-size:12px; font-weight:600; color:var(--ink3); text-transform:uppercase; letter-spacing:.05em; display:flex; justify-content:space-between; margin-bottom:5px; }
.cpr { font-size:11px; color:var(--ink3); margin-bottom:3px; line-height:1.5; }
.cpr span { color:var(--ink2); }
.cthesis { font-size:12px; color:var(--ink2); line-height:1.7; margin-top:8px; border-top:1px solid var(--border2); padding-top:10px; }

/* ── Disclaimer ── */
.disclaimer { padding:16px 24px; color:var(--ink4); font-size:10px; border-top:1px solid var(--border); line-height:1.6; }

/* ── Responsive ── */
@media (max-width:760px) {
  :root { --header-h:50px; --controls-h:42px; }
  header { padding:0 12px; }
  .logo small { display:none; }
  .controls { padding:0 10px; gap:6px; }
  .controls input { width:110px; }
  #desktop-table { display:none; }
  #mobile-list { display:block; }
  .pillars { grid-template-columns:1fr; }
  .entry-exit { grid-template-columns:repeat(3,1fr); }
}
@media (max-width:380px) {
  .card-levels { grid-template-columns:1fr 1fr; }
  .entry-exit { grid-template-columns:repeat(2,1fr); }
}
</style>
</head>
<body>

<header>
  <div class="logo">Market Scanner <small>Technical &middot; Volume &middot; Lynch</small></div>
  <div class="updated">{updated}</div>
</header>

<div class="controls">
  <input type="text" id="srch" placeholder="Search ticker or name...">
  <select id="sigF"><option value="">All signals</option><option value="strong-buy">Strong Buy</option><option value="buy">Buy</option><option value="hold">Hold</option><option value="caution">Caution</option></select>
  <select id="lynF"><option value="">All Lynch</option><option value="Fast Grower">Fast Grower</option><option value="Stalwart">Stalwart</option><option value="Cyclical">Cyclical</option><option value="Turnaround">Turnaround</option><option value="Slow Grower">Slow Grower</option><option value="Asset Play">Asset Play</option><option value="ETF">ETF</option></select>
  <select id="volF"><option value="">All volume</option><option value="Accumulation">Accumulation</option><option value="Distribution">Distribution</option><option value="Neutral">Neutral</option></select>
  <select id="mktF"><option value="">US + CA</option><option value="us">US only</option><option value="ca">Canada only</option></select>
  <select id="typF"><option value="">Stocks + ETFs</option><option value="stock">Stocks</option><option value="etf">ETFs</option></select>
  <div class="stats" id="stats"></div>
</div>

<div id="desktop-table">
<table>
<thead><tr>
  <th data-k="ticker">Ticker</th>
  <th data-k="name">Name</th>
  <th data-k="price" style="text-align:right">Price</th>
  <th data-k="ytd" style="text-align:right">YTD %</th>
  <th data-k="rsi" style="text-align:right">RSI</th>
  <th data-k="signal">Signal</th>
  <th data-k="lynch_cat">Lynch</th>
  <th data-k="peg" style="text-align:right">PEG</th>
  <th data-k="vol_label">Volume</th>
  <th data-k="composite" style="text-align:right">Score</th>
  <th data-k="rr" style="text-align:right">R:R</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
</div>

<div id="mobile-list"></div>

<div class="disclaimer">
  Not financial advice. Signals are algorithmic estimates. Peter Lynch categories are approximations.
  Always verify on your broker before trading. Data: Yahoo Finance.
</div>

<script>
const D = {data_json};
let sk='composite', sd=-1, openCard=null, openRow=null;

const sc = s => s>=1?'score-pos':s<=-1?'score-neg':'score-neu';
const rc = r => r>=2?'rr-good':r>=1?'rr-ok':'rr-bad';
const pc = p => p==null?'':p<1?'peg-good':p<2?'peg-fair':'peg-bad';
const vi = l => !l?'—':l.includes('Accum')||l.includes('Strong')?'&#9650; '+l:l.includes('Distrib')?'&#9660; '+l:l;
const ps = (s,n) => `<span class="ps ${sc(s)}">${s>0?'+':''}${s}</span>`;
const sign = n => n>=0?'+':'';
const ytdCl = n => n>=0?'ytd-pos':'ytd-neg';
const fmtP = v => v!=null?v.toFixed(2):'—';

function detail(d) {
  return `<div class="detail-panel">
    <div class="pillars">
      <div class="pillar"><h4>Technical ${ps(d.tech_score)}</h4>
        <div class="pr">Trend: <span>${d.factors}</span></div>
        <div class="pr">RSI: <span>${d.rsi}${d.rsi<35?' — oversold':d.rsi>70?' — overbought':''}</span></div>
        <div class="pr">YTD: <span class="${ytdCl(d.ytd)}">${sign(d.ytd)}${d.ytd.toFixed(1)}%</span></div>
      </div>
      <div class="pillar"><h4>Volume ${ps(d.vol_score)}</h4>
        <div class="pr">OBV: <span>${d.obv_signal||'—'}</span></div>
        <div class="pr">Surge: <span>${d.surge_signal||'—'}</span></div>
        <div class="pr">P/V: <span>${d.pv_confirm||'—'}</span></div>
        ${d.pullback_signal?`<div class="pr">Pullback: <span>${d.pullback_signal}</span></div>`:''}
      </div>
      <div class="pillar"><h4>Lynch: ${d.lynch_cat} ${ps(d.lynch_score)}</h4>
        ${d.peg_signal?`<div class="pr"><span>${d.peg_signal}</span></div>`:''}
        ${d.growth_signal?`<div class="pr"><span>${d.growth_signal}</span></div>`:''}
        ${d.debt_signal?`<div class="pr"><span>${d.debt_signal}</span></div>`:''}
        ${d.roe_signal?`<div class="pr"><span>${d.roe_signal}</span></div>`:''}
        ${d.fcf_signal?`<div class="pr"><span>${d.fcf_signal}</span></div>`:''}
      </div>
    </div>
    <div class="entry-exit">
      <div class="ee"><h4>Entry</h4><div class="ev">$${d.entry_low.toFixed(2)}</div><div class="ev">$${d.entry_high.toFixed(2)}</div><div class="es">Buy zone</div></div>
      <div class="ee"><h4>Stop</h4><div class="ev sv">$${d.stop.toFixed(2)}</div><div class="es">Exit if breaks</div></div>
      <div class="ee"><h4>Target 1</h4><div class="ev tv">$${d.t1.toFixed(2)}</div><div class="es">Scale 50%</div></div>
      <div class="ee"><h4>Target 2</h4><div class="ev tv">$${d.t2.toFixed(2)}</div><div class="es">Trail stop</div></div>
      <div class="ee"><h4>R:R</h4><div class="ev"><span class="signal-badge ${rc(d.rr)}">${d.rr.toFixed(2)}:1</span></div><div class="es">Min 2:1</div></div>
      <div class="ee"><h4>Size</h4><div class="ev">${d.position_size}</div><div class="es">of portfolio</div></div>
    </div>
    <div class="alert-box"><strong>When to act:</strong> ${d.alert}</div>
    <div class="thesis-box"><h4>Thesis</h4><p>${d.thesis}</p></div>
  </div>`;
}

function renderDesktop(data) {
  const tbody = document.getElementById('tbody');
  let html='', lastSec='';
  data.forEach((d,i) => {
    const sec = d.is_etf?(d.ticker.endsWith('.TO')?'Canadian ETFs':'US ETFs'):(d.ticker.endsWith('.TO')?'Canadian Stocks':'US Stocks');
    if(sec!==lastSec){html+=`<tr class="section-header"><td colspan="11">${sec}</td></tr>`;lastSec=sec;}
    const pg = d.peg!=null?`<span class="${pc(d.peg)}">${d.peg.toFixed(2)}</span>`:'—';
    html+=`<tr class="stock-row${openRow===i?' expanded':''}" id="dr${i}" onclick="toggleRow(${i})">
      <td class="tc">${d.ticker}</td><td class="nc">${d.name}</td>
      <td class="mc">$${d.price.toFixed(2)}</td>
      <td class="mc ${ytdCl(d.ytd)}">${sign(d.ytd)}${d.ytd.toFixed(1)}%</td>
      <td class="mc">${d.rsi}</td>
      <td><span class="signal-badge ${d.signal_class}">${d.signal}</span></td>
      <td class="lc">${d.lynch_cat||'—'}</td>
      <td class="mc">${pg}</td>
      <td class="vc">${vi(d.vol_label)}</td>
      <td class="mc">${d.composite.toFixed(1)}</td>
      <td class="mc"><span class="signal-badge ${rc(d.rr)}">${d.rr.toFixed(1)}:1</span></td>
    </tr>
    <tr class="detail-row" id="dd${i}" style="display:${openRow===i?'table-row':'none'}">
      <td colspan="11">${detail(d)}</td>
    </tr>`;
  });
  tbody.innerHTML = html;
}

function renderMobile(data) {
  const ml = document.getElementById('mobile-list');
  let html='';
  data.forEach((d,i) => {
    const inZone = d.price>=d.entry_low && d.price<=d.entry_high;
    const aboveZone = d.price>d.entry_high;
    const hint = inZone?'In entry zone now':aboveZone?'Wait — above entry zone':'Below entry zone';
    html+=`<div class="card${openCard===i?' open':''}" id="mc${i}">
      <div class="card-bar ${d.signal_class}"></div>
      <div class="card-top" onclick="toggleCard(${i})">
        <div class="card-left">
          <div class="cticker">${d.ticker} <span class="signal-badge ${d.signal_class}">${d.signal}</span></div>
          <div class="cname">${d.name}</div>
        </div>
        <div class="card-chevron">&#9660;</div>
      </div>
      <div class="card-meta" onclick="toggleCard(${i})">
        <span class="cmeta">${d.lynch_cat||'—'}</span>
        <span class="cmeta">PEG <strong class="${pc(d.peg)}">${fmtP(d.peg)}</strong></span>
        <span class="cmeta ${ytdCl(d.ytd)}">YTD ${sign(d.ytd)}${d.ytd.toFixed(1)}%</span>
        <span class="cmeta">${vi(d.vol_label)}</span>
        <span class="cmeta">RSI ${d.rsi}</span>
      </div>
      <div class="card-price" onclick="toggleCard(${i})">
        <div><div class="cprice-label">Current Price</div><div class="cprice-val">$${d.price.toFixed(2)}</div></div>
        <div class="cprice-hint">${hint}<br><span style="color:var(--ink4)">Entry $${d.entry_low.toFixed(2)}–$${d.entry_high.toFixed(2)}</span></div>
      </div>
      <div class="card-levels" onclick="toggleCard(${i})">
        <div class="cl"><h5>Stop Loss</h5><div class="clv red">$${d.stop.toFixed(2)}</div><div class="cls">Exit if broken</div></div>
        <div class="cl"><h5>Target 1</h5><div class="clv green">$${d.t1.toFixed(2)}</div><div class="cls">Scale 50%</div></div>
        <div class="cl"><h5>Target 2</h5><div class="clv green">$${d.t2.toFixed(2)}</div><div class="cls">Trail stop</div></div>
        <div class="cl"><h5>R:R &nbsp; Size</h5><div class="clv"><span class="signal-badge ${rc(d.rr)}">${d.rr.toFixed(1)}:1</span></div><div class="cls">${d.position_size}</div></div>
      </div>
      <div class="card-alert"><strong>When to act:</strong> ${d.alert}</div>
      <div class="card-expand">
        <div class="cpillar"><h4>Technical ${ps(d.tech_score)}</h4>
          <div class="cpr">Trend: <span>${d.factors}</span></div>
          <div class="cpr">RSI ${d.rsi}${d.rsi<35?' — oversold':d.rsi>70?' — overbought':''}</div>
        </div>
        <div class="cpillar"><h4>Volume ${ps(d.vol_score)}</h4>
          <div class="cpr"><span>${d.obv_signal||'—'}</span></div>
          <div class="cpr"><span>${d.surge_signal||'—'}</span></div>
        </div>
        <div class="cpillar"><h4>Lynch: ${d.lynch_cat} ${ps(d.lynch_score)}</h4>
          ${d.peg_signal?`<div class="cpr"><span>${d.peg_signal}</span></div>`:''}
          ${d.growth_signal?`<div class="cpr"><span>${d.growth_signal}</span></div>`:''}
          ${d.debt_signal?`<div class="cpr"><span>${d.debt_signal}</span></div>`:''}
        </div>
        <div class="cthesis">${d.thesis}</div>
      </div>
    </div>`;
  });
  ml.innerHTML = html || '<p style="text-align:center;padding:32px;color:var(--ink4);">No results</p>';
}

function toggleRow(i) {
  if(openRow===i){document.getElementById('dd'+i).style.display='none';document.getElementById('dr'+i).classList.remove('expanded');openRow=null;}
  else{
    if(openRow!==null){document.getElementById('dd'+openRow).style.display='none';document.getElementById('dr'+openRow).classList.remove('expanded');}
    document.getElementById('dd'+i).style.display='table-row';document.getElementById('dr'+i).classList.add('expanded');openRow=i;
  }
}

function toggleCard(i) {
  const prev=openCard;
  if(prev===i){document.getElementById('mc'+i).classList.remove('open');openCard=null;}
  else{
    if(prev!==null)document.getElementById('mc'+prev).classList.remove('open');
    document.getElementById('mc'+i).classList.add('open');openCard=i;
  }
}

function filtered() {
  const s=document.getElementById('srch').value.toLowerCase();
  const sig=document.getElementById('sigF').value;
  const lyn=document.getElementById('lynF').value;
  const vol=document.getElementById('volF').value;
  const mkt=document.getElementById('mktF').value;
  const typ=document.getElementById('typF').value;
  openRow=null; openCard=null;
  return [...D].filter(d=>
    (!s||d.ticker.toLowerCase().includes(s)||d.name.toLowerCase().includes(s))
    &&(!sig||d.signal_class===sig)
    &&(!lyn||d.lynch_cat===lyn)
    &&(!vol||(d.vol_label||'').includes(vol))
    &&(!mkt||(mkt==='ca'?d.ticker.endsWith('.TO'):!d.ticker.endsWith('.TO')))
    &&(!typ||(typ==='etf'?d.is_etf:!d.is_etf))
  ).sort((a,b)=>{
    const av=a[sk]??0,bv=b[sk]??0;
    if(av==null)return 1;if(bv==null)return -1;
    return typeof av==='string'?sd*av.localeCompare(bv):sd*(av-bv);
  });
}

function render() {
  const data=filtered();
  renderDesktop(data);
  renderMobile(data);
  document.getElementById('stats').textContent=data.length+' instruments';
  document.querySelectorAll('thead th').forEach(th=>{th.classList.remove('asc','desc');if(th.dataset.k===sk)th.classList.add(sd===-1?'desc':'asc');});
}

document.querySelectorAll('thead th[data-k]').forEach(th=>{
  th.addEventListener('click',()=>{const k=th.dataset.k;sd=(sk===k)?sd*-1:-1;sk=k;render();});
});
['srch','sigF','lynF','volF','mktF','typF'].forEach(id=>{
  const el=document.getElementById(id);
  el.addEventListener(id==='srch'?'input':'change',render);
});

render();
</script>
</body>
</html>"""


# ─── EMAIL GENERATOR ─────────────────────────────────────────────────────────

def generate_email_html(results, updated):
    """
    Mobile-first card layout. Top 15 signals only.
    Priority: Strong Buy + R:R>=2, then Strong Buy any R:R, then Buy + R:R>=2.
    Font: Calibri/system stack. Single column. No tables for layout.
    """
    now_et = datetime.now(ZoneInfo("America/New_York"))
    period = "Morning Open" if now_et.hour < 14 else "Afternoon Close"
    subject_date = now_et.strftime("%B %d, %Y")

    # Priority tiers — capped at 15 total to stay under Gmail's 102KB clip
    tier1 = [r for r in results if r["signal"] == "Strong Buy" and r["rr"] >= 2.0]
    tier2 = [r for r in results if r["signal"] == "Strong Buy" and r["rr"] < 2.0]
    tier3 = [r for r in results if r["signal"] == "Buy" and r["rr"] >= 2.0]
    for t in (tier1, tier2, tier3):
        t.sort(key=lambda x: -x["composite"])
    actionable = (tier1 + tier2 + tier3)[:15]

    strong_buy_count = sum(1 for r in actionable if r["signal"] == "Strong Buy")
    buy_count = len(actionable) - strong_buy_count

    F = "Calibri, 'Gill Sans', Arial, sans-serif"

    def tag(signal):
        if signal == "Strong Buy":
            return (f'<span style="background:#1a4a1a;color:#d4edda;padding:3px 10px;'
                    f'border-radius:4px;font-size:12px;font-weight:700;font-family:{F};">'
                    f'STRONG BUY</span>')
        return (f'<span style="background:#2d5a27;color:#fff;padding:3px 10px;'
                f'border-radius:4px;font-size:12px;font-weight:700;font-family:{F};">'
                f'BUY</span>')

    def rr_color(rr):
        return "#1a6b1a" if rr >= 2 else "#c47a00"

    def peg_str(peg):
        if peg is None:
            return "—"
        color = "#1a6b1a" if peg < 1 else "#c47a00" if peg < 2 else "#b02020"
        return f'<span style="color:{color};font-weight:700;">{peg:.2f}</span>'

    def vol_icon(lbl):
        if not lbl:
            return "—"
        if "Accum" in lbl or "Strong" in lbl:
            return f"&#9650; {lbl}"
        if "Distrib" in lbl:
            return f"&#9660; {lbl}"
        return lbl

    cards = ""
    if not actionable:
        cards = (f'<p style="font-family:{F};font-size:15px;color:#555;text-align:center;'
                 f'padding:32px 16px;">No actionable signals today. '
                 f'Market conditions are mixed &mdash; patience is a position.</p>')
    else:
        for i, r in enumerate(actionable):
            ytd_color = "#1a6b1a" if r["ytd"] >= 0 else "#b02020"
            ytd_str = f'{"+" if r["ytd"]>=0 else ""}{r["ytd"]:.1f}%'
            border_color = "#1a4a1a" if r["signal"] == "Strong Buy" else "#2d5a27"
            thesis_short = r["thesis"][:180] + "..." if len(r["thesis"]) > 180 else r["thesis"]

            cards += f"""
<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;border:1px solid #ddd;border-left:4px solid {border_color};border-radius:6px;background:#ffffff;font-family:{F};">

  <!-- Card header: rank + ticker + signal -->
  <tr>
    <td style="padding:14px 16px 10px 16px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="vertical-align:middle;">
            <span style="font-size:11px;color:#888;font-family:{F};">#{i+1}</span>&nbsp;
            <span style="font-size:22px;font-weight:700;color:#111;font-family:{F};">{r['ticker']}</span>&nbsp;
            <span style="font-size:14px;color:#444;font-family:{F};">{r['name']}</span>
          </td>
          <td style="text-align:right;vertical-align:middle;white-space:nowrap;">
            {tag(r['signal'])}
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Tags row: Lynch, PEG, YTD, Volume -->
  <tr>
    <td style="padding:0 16px 12px 16px;">
      <span style="font-size:12px;color:#555;font-family:{F};">
        {r.get('lynch_cat','—')} &nbsp;&bull;&nbsp;
        PEG {peg_str(r['peg'])} &nbsp;&bull;&nbsp;
        YTD <span style="color:{ytd_color};font-weight:600;">{ytd_str}</span> &nbsp;&bull;&nbsp;
        {vol_icon(r.get('vol_label',''))}
      </span>
    </td>
  </tr>

  <!-- Current price bar -->
  <tr>
    <td style="background:#f0f0f0;padding:10px 16px;border-top:1px solid #e0e0e0;border-bottom:1px solid #e0e0e0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="vertical-align:middle;">
            <span style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.06em;font-family:{F};">Current Price</span>
            <span style="font-size:22px;font-weight:700;color:#111;font-family:{F};margin-left:10px;">${r['price']:.2f}</span>
          </td>
          <td style="text-align:right;vertical-align:middle;">
            <span style="font-size:12px;color:#888;font-family:{F};">
              {'&#9650; Entry is below current — wait for pullback' if r['entry_high'] < r['price'] else '&#9989; Price is in entry zone now'}
            </span>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Price grid: 4 columns -->
  <tr>
    <td style="padding:12px 16px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="width:25%;padding-right:8px;vertical-align:top;">
            <div style="font-size:10px;color:#888;text-transform:uppercase;letter-spacing:0.06em;font-family:{F};margin-bottom:3px;">Entry Zone</div>
            <div style="font-size:15px;font-weight:700;color:#111;font-family:{F};">${r['entry_low']:.2f}</div>
            <div style="font-size:13px;color:#555;font-family:{F};">to ${r['entry_high']:.2f}</div>
          </td>
          <td style="width:25%;padding-right:8px;vertical-align:top;">
            <div style="font-size:10px;color:#888;text-transform:uppercase;letter-spacing:0.06em;font-family:{F};margin-bottom:3px;">Stop Loss</div>
            <div style="font-size:15px;font-weight:700;color:#b02020;font-family:{F};">${r['stop']:.2f}</div>
            <div style="font-size:11px;color:#888;font-family:{F};">Exit if broken</div>
          </td>
          <td style="width:25%;padding-right:8px;vertical-align:top;">
            <div style="font-size:10px;color:#888;text-transform:uppercase;letter-spacing:0.06em;font-family:{F};margin-bottom:3px;">Targets</div>
            <div style="font-size:13px;color:#1a6b1a;font-weight:600;font-family:{F};">T1 ${r['t1']:.2f}</div>
            <div style="font-size:13px;color:#1a6b1a;font-family:{F};">T2 ${r['t2']:.2f}</div>
          </td>
          <td style="width:25%;vertical-align:top;">
            <div style="font-size:10px;color:#888;text-transform:uppercase;letter-spacing:0.06em;font-family:{F};margin-bottom:3px;">R:R &nbsp;|&nbsp; Size</div>
            <div style="font-size:18px;font-weight:700;color:{rr_color(r['rr'])};font-family:{F};">{r['rr']:.1f}:1</div>
            <div style="font-size:11px;color:#555;font-family:{F};">{r['position_size']} portfolio</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Alert -->
  <tr>
    <td style="padding:0 16px 10px 16px;">
      <div style="background:#f5f5f5;border-radius:4px;padding:10px 12px;font-size:13px;color:#333;font-family:{F};line-height:1.5;">
        <span style="font-weight:700;color:#444;">When to act:</span> {r['alert']}
      </div>
    </td>
  </tr>

  <!-- Thesis -->
  <tr>
    <td style="padding:0 16px 14px 16px;">
      <div style="font-size:12px;color:#666;line-height:1.6;font-family:{F};">{thesis_short}</div>
    </td>
  </tr>

</table>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ margin:0;padding:0;background:#f0f0f0; }}
  @media only screen and (max-width:600px) {{
    .outer {{ padding:12px 8px !important; }}
    .container {{ border-radius:0 !important; }}
  }}
</style>
</head>
<body>
<div class="outer" style="background:#f0f0f0;padding:24px 16px;">
<div class="container" style="max-width:600px;margin:0 auto;background:#f8f8f8;border-radius:8px;overflow:hidden;font-family:{F};">

  <!-- Header -->
  <div style="background:#111;padding:20px 20px 16px 20px;">
    <div style="font-size:20px;font-weight:700;color:#fff;font-family:{F};letter-spacing:-0.3px;">Market Scanner</div>
    <div style="font-size:13px;color:#888;margin-top:4px;font-family:{F};">{period} &nbsp;&middot;&nbsp; {subject_date} &nbsp;&middot;&nbsp; Technical + Volume + Lynch</div>
  </div>

  <!-- Summary strip -->
  <div style="background:#222;padding:10px 20px;font-family:{F};font-size:13px;">
    <span style="color:#6fcf6f;font-weight:700;">{strong_buy_count} Strong Buy</span>
    <span style="color:#555;">&nbsp;&nbsp;|&nbsp;&nbsp;</span>
    <span style="color:#a8d8a8;">{buy_count} Buy</span>
    <span style="color:#555;">&nbsp;&nbsp;|&nbsp;&nbsp;</span>
    <span style="color:#666;">Top {len(actionable)} signals &middot; Sorted by priority</span>
  </div>

  <!-- Cards -->
  <div style="padding:16px 12px;">
    {cards}
  </div>

  <!-- Footer -->
  <div style="background:#111;padding:14px 20px;font-size:11px;color:#555;line-height:1.7;font-family:{F};">
    R:R = Risk to Reward. Only trade setups with R:R &ge; 2:1 &mdash; risk $1 to make $2+.<br>
    Not financial advice. Always verify on your broker before acting.<br>
    <a href="https://gtmautomationops-dev.github.io/market-scanner/" style="color:#6fcf6f;">Full dashboard &rarr;</a>
  </div>

</div>
</div>
</body>
</html>"""

    return html, f"Market Scanner — {period} — {subject_date}"


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_scan():
    all_tickers_ordered = US_STOCKS + US_ETFS + CA_STOCKS + CA_ETFS
    seen, tickers = set(), []
    for t in all_tickers_ordered:
        if t not in seen:
            seen.add(t)
            tickers.append(t)

    print(f"Scanning {len(tickers)} tickers with Technical + Volume + Lynch scoring...")
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
                hist = (data[ticker] if len(batch) > 1 and ticker in data.columns.get_level_values(0)
                        else (data if len(batch) == 1 else None))
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
    results.sort(key=lambda x: (-x["composite"], signal_order.get(x["signal"], 4), x["ticker"]))

    updated = datetime.now().strftime("%B %d, %Y at %H:%M ET")
    html = HTML_TEMPLATE.replace("{updated}", updated).replace(
        "{data_json}", json.dumps(results, ensure_ascii=False)
    )

    out = Path("docs")
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"Done. Dashboard written to docs/index.html")

    email_html, subject = generate_email_html(results, updated)
    (out / "email_alert.html").write_text(email_html, encoding="utf-8")
    (out / "email_subject.txt").write_text(subject, encoding="utf-8")
    print(f"Email alert written to docs/email_alert.html")
    print(f"Subject: {subject}")


if __name__ == "__main__":
    run_scan()
