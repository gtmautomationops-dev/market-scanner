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

    eg = (eps_growth or 0) * 100  # as percentage

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
    elif eg < 0 and profit_margin and profit_margin > -0.05:
        category = "Turnaround"
        details["category_desc"] = "Currently struggling. Lynch looks for catalyst and improving cash flow."
    elif div_yield > 0.04 and eg < 10:
        category = "Slow Grower"
        details["category_desc"] = "Low growth, income-focused. Lynch owns for yield, not capital gains."
    elif total_cash > market_cap * 0.3 and market_cap > 0:
        category = "Asset Play"
        details["category_desc"] = "Assets worth more than market price. Lynch hunts hidden balance sheet value."
    else:
        category = "Stalwart"
        details["category_desc"] = "Solid large-cap. Moderate growth expectations."

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
    high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
    low_52w = min(closes[-252:]) if len(closes) >= 252 else min(closes)
    volatility = (high_52w - low_52w) / low_52w if low_52w > 0 else 0.3
    stop_pct = max(0.08, min(0.18, volatility * 0.25))
    stop = entry_mid * (1 - stop_pct)
    t1 = entry_mid * 1.175
    t2 = entry_mid * 1.35
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

        if composite >= 3.0:
            signal, signal_class = "Strong Buy", "strong-buy"
        elif composite >= 1.0:
            signal, signal_class = "Buy", "buy"
        elif composite >= -0.5:
            signal, signal_class = "Hold", "hold"
        else:
            signal, signal_class = "Caution", "caution"

        entry_low, entry_high, entry_mid, stop, t1, t2, rr, position_size, setup, alert = (
            compute_entry_exit(current, closes, price_vs_ma20, range_pct, composite)
        )

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
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #f4efe6; color: #2c2419; font-family: 'IBM Plex Mono', monospace; font-size: 13px; line-height: 1.5; }
header { background: #faf7f1; border-bottom: 1px solid #d4c9b8; padding: 20px 32px; display: flex; justify-content: space-between; align-items: center; }
.logo { font-family: 'EB Garamond', serif; font-size: 22px; font-weight: 600; color: #1a1008; }
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

/* Detail panel */
.detail-panel { padding: 20px 24px; }
.pillars { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.pillar { background: #faf7f1; border: 1px solid #d4c9b8; border-radius: 6px; padding: 14px 16px; }
.pillar h4 { font-family: 'EB Garamond', serif; font-size: 13px; font-weight: 600; color: #5c4a35; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.06em; display: flex; justify-content: space-between; align-items: center; }
.pillar-score { font-family: 'IBM Plex Mono', monospace; font-size: 12px; padding: 1px 7px; border-radius: 3px; font-weight: 500; }
.score-pos { background: #d4edda; color: #1a4a1a; }
.score-neg { background: #f5ddd8; color: #7a2020; }
.score-neu { background: #f5edcc; color: #6b5400; }
.pillar-row { font-size: 11px; color: #5c4a35; margin-bottom: 5px; line-height: 1.5; }
.pillar-row span { color: #2c2419; font-weight: 500; }

/* Entry/exit row */
.entry-exit { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 16px; background: #faf7f1; border: 1px solid #d4c9b8; border-radius: 6px; padding: 14px 16px; }
.ee-block h4 { font-family: 'EB Garamond', serif; font-size: 11px; font-weight: 600; color: #8a7560; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
.ee-block .val { font-family: 'IBM Plex Mono', monospace; font-size: 13px; font-weight: 500; color: #1a1008; }
.ee-block .val.stop { color: #7a2020; }
.ee-block .val.target { color: #2d5a27; }
.ee-block .sub { font-size: 10px; color: #8a7560; }

/* Alert + thesis */
.alert-box { background: #fdf8ef; border: 1px solid #e8d98a; border-radius: 4px; padding: 10px 14px; font-size: 12px; color: #1a1008; margin-bottom: 12px; }
.alert-box strong { color: #6b5400; }
.thesis-box h4 { font-family: 'EB Garamond', serif; font-size: 13px; font-weight: 600; color: #5c4a35; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.06em; }
.thesis-box p { font-size: 12px; line-height: 1.7; color: #2c2419; }

/* Table cells */
.ticker-cell { font-family: 'IBM Plex Mono', monospace; font-size: 13px; font-weight: 500; color: #1a1008; min-width: 90px; }
.name-cell { font-family: 'EB Garamond', serif; font-size: 12px; font-weight: 500; color: #2c2419; min-width: 180px; max-width: 180px; }
.price-cell { font-family: 'IBM Plex Mono', monospace; text-align: right; }
.ytd-cell { font-family: 'IBM Plex Mono', monospace; text-align: right; }
.ytd-pos { color: #2d5a27; }
.ytd-neg { color: #7a2020; }
.num-cell { font-family: 'IBM Plex Mono', monospace; text-align: right; color: #5c4a35; font-size: 12px; }
.factors-cell { font-size: 11px; font-weight: 500; color: #5c4a35; min-width: 150px; max-width: 160px; }
.lynch-cell { font-size: 11px; color: #5c4a35; white-space: nowrap; }
.vol-cell { font-size: 11px; color: #5c4a35; white-space: nowrap; }

.signal-badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 500; white-space: nowrap; }
.strong-buy { background: #d4edda; color: #1a4a1a; border: 1px solid #b8d9c0; }
.buy { background: #ddefd6; color: #2d5a27; border: 1px solid #c4ddb8; }
.hold { background: #f5edcc; color: #6b5400; border: 1px solid #e8d98a; }
.caution { background: #f5ddd8; color: #7a2020; border: 1px solid #e8c4bc; }

.peg-good { color: #2d5a27; font-weight: 500; }
.peg-fair { color: #6b5400; }
.peg-bad { color: #7a2020; }
.rr-good { color: #2d5a27; }
.rr-ok { color: #5c4a35; }
.rr-bad { color: #7a2020; }

.section-header td { background: #ede8de; font-family: 'EB Garamond', serif; font-size: 13px; font-weight: 600; color: #5c4a35; padding: 10px 12px 6px; letter-spacing: 0.04em; border-top: 2px solid #d4c9b8; cursor: default; }
.disclaimer { padding: 20px 32px; color: #8a7560; font-size: 10px; border-top: 1px solid #d4c9b8; line-height: 1.6; }
.stars { color: #c4a020; }
</style>
</head>
<body>
<header>
  <div class="logo">Market Scanner <span>Technical + Volume + Lynch</span></div>
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
  <label>Lynch:</label>
  <select id="lynchFilter">
    <option value="">All categories</option>
    <option value="Fast Grower">Fast Grower</option>
    <option value="Stalwart">Stalwart</option>
    <option value="Cyclical">Cyclical</option>
    <option value="Turnaround">Turnaround</option>
    <option value="Slow Grower">Slow Grower</option>
    <option value="Asset Play">Asset Play</option>
    <option value="ETF">ETF</option>
  </select>
  <label>Volume:</label>
  <select id="volFilter">
    <option value="">All</option>
    <option value="Accumulation">Accumulation</option>
    <option value="Distribution">Distribution</option>
    <option value="Neutral">Neutral</option>
  </select>
  <label>Market:</label>
  <select id="marketFilter">
    <option value="">US + CA</option>
    <option value="us">US only</option>
    <option value="ca">Canada only</option>
  </select>
  <label>Type:</label>
  <select id="typeFilter">
    <option value="">All types</option>
    <option value="stock">Stocks</option>
    <option value="etf">ETFs</option>
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
  <th data-key="lynch_cat">Lynch Cat.</th>
  <th data-key="peg" style="text-align:right">PEG</th>
  <th data-key="vol_label">Volume</th>
  <th>Factors</th>
  <th data-key="rr" style="text-align:right">R:R</th>
</tr></thead>
<tbody id="tableBody"></tbody>
</table>
<div class="disclaimer">
  Not financial advice. Signals are algorithmic estimates based on price action, volume, and publicly available fundamentals.
  Peter Lynch framework classifications are approximations based on available data. Always do your own research before trading.
  Data: Yahoo Finance via yfinance.
</div>
<script>
const allData = {data_json};
let sortKey = 'composite', sortDir = -1, expandedRow = null;

function scoreClass(s) { return s >= 1 ? 'score-pos' : s <= -1 ? 'score-neg' : 'score-neu'; }
function rrClass(rr) { return rr >= 2 ? 'rr-good' : rr >= 1 ? 'rr-ok' : 'rr-bad'; }
function pegClass(p) { return p < 1 ? 'peg-good' : p < 2 ? 'peg-fair' : 'peg-bad'; }
function fmt(v, dec, suffix) { return v != null ? v.toFixed(dec) + (suffix||'') : '—'; }
function fmtAUM(v) {
  if (!v) return '—';
  if (v >= 1e9) return '$' + (v/1e9).toFixed(1)+'B';
  if (v >= 1e6) return '$' + (v/1e6).toFixed(0)+'M';
  return '$'+v;
}
function lynchIcon(cat) {
  const m = {'Fast Grower':'&#128640;','Stalwart':'&#127959;','Cyclical':'&#128260;',
    'Turnaround':'&#128257;','Slow Grower':'&#128022;','Asset Play':'&#128142;','ETF':'&#128202;'};
  return (m[cat]||'') + ' ' + (cat||'—');
}
function volIcon(lbl) {
  if (!lbl) return '—';
  if (lbl.includes('Accum') || lbl.includes('Strong')) return '&#9650; ' + lbl;
  if (lbl.includes('Distrib')) return '&#9660; ' + lbl;
  return lbl;
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
    const ytdCls = d.ytd >= 0 ? 'ytd-pos' : 'ytd-neg';
    const pegStr = d.peg != null ? `<span class="${pegClass(d.peg)}">${d.peg.toFixed(2)}</span>` : '—';

    html += `<tr class="stock-row" id="row-${idx}" onclick="toggleDetail(${idx})">
      <td class="ticker-cell">${d.ticker}</td>
      <td class="name-cell">${d.name}</td>
      <td class="price-cell">$${d.price.toFixed(2)}</td>
      <td class="ytd-cell ${ytdCls}">${ytdSign}${d.ytd.toFixed(1)}%</td>
      <td class="num-cell">${d.rsi}</td>
      <td><span class="signal-badge ${d.signal_class}">${d.signal}</span></td>
      <td class="lynch-cell">${lynchIcon(d.lynch_cat)}</td>
      <td class="num-cell">${pegStr}</td>
      <td class="vol-cell">${volIcon(d.vol_label)}</td>
      <td class="factors-cell">${d.factors}</td>
      <td class="${rrClass(d.rr)} num-cell">${d.rr.toFixed(1)}:1</td>
    </tr>
    <tr class="detail-row" id="detail-${idx}" style="display:none"><td colspan="11">
      <div class="detail-panel">

        <div class="pillars">
          <div class="pillar">
            <h4>Technical <span class="pillar-score ${scoreClass(d.tech_score)}">${d.tech_score > 0 ? '+' : ''}${d.tech_score}</span></h4>
            <div class="pillar-row">Trend: <span>${d.factors}</span></div>
            <div class="pillar-row">RSI: <span>${d.rsi} ${d.rsi < 35 ? '— oversold' : d.rsi > 70 ? '— overbought' : '— neutral'}</span></div>
            <div class="pillar-row">YTD: <span class="${d.ytd>=0?'ytd-pos':'ytd-neg'}">${d.ytd>=0?'+':''}${d.ytd.toFixed(1)}%</span></div>
          </div>
          <div class="pillar">
            <h4>Volume Flow <span class="pillar-score ${scoreClass(d.vol_score)}">${d.vol_score > 0 ? '+' : ''}${d.vol_score}</span></h4>
            <div class="pillar-row">OBV: <span>${d.obv_signal || '—'}</span></div>
            <div class="pillar-row">Surge: <span>${d.surge_signal || '—'}</span></div>
            <div class="pillar-row">Price/Vol: <span>${d.pv_confirm || '—'}</span></div>
            ${d.pullback_signal ? `<div class="pillar-row">Pullback: <span>${d.pullback_signal}</span></div>` : ''}
          </div>
          <div class="pillar">
            <h4>Lynch: ${d.lynch_cat} <span class="pillar-score ${scoreClass(d.lynch_score)}">${d.lynch_score > 0 ? '+' : ''}${d.lynch_score}</span></h4>
            ${d.peg_signal ? `<div class="pillar-row"><span>${d.peg_signal}</span></div>` : ''}
            ${d.growth_signal ? `<div class="pillar-row"><span>${d.growth_signal}</span></div>` : ''}
            ${d.debt_signal ? `<div class="pillar-row"><span>${d.debt_signal}</span></div>` : ''}
            ${d.roe_signal ? `<div class="pillar-row"><span>${d.roe_signal}</span></div>` : ''}
            ${d.fcf_signal ? `<div class="pillar-row"><span>${d.fcf_signal}</span></div>` : ''}
          </div>
        </div>

        <div class="entry-exit">
          <div class="ee-block">
            <h4>Entry Zone</h4>
            <div class="val">$${d.entry_low.toFixed(2)}</div>
            <div class="val">$${d.entry_high.toFixed(2)}</div>
            <div class="sub">Buy between</div>
          </div>
          <div class="ee-block">
            <h4>Stop Loss</h4>
            <div class="val stop">$${d.stop.toFixed(2)}</div>
            <div class="sub">Exit if breaks</div>
          </div>
          <div class="ee-block">
            <h4>Target 1</h4>
            <div class="val target">$${d.t1.toFixed(2)}</div>
            <div class="sub">Scale out 50%</div>
          </div>
          <div class="ee-block">
            <h4>Target 2</h4>
            <div class="val target">$${d.t2.toFixed(2)}</div>
            <div class="sub">Trail stop</div>
          </div>
          <div class="ee-block">
            <h4>Risk / Reward</h4>
            <div class="val ${rrClass(d.rr)}">${d.rr.toFixed(2)}:1</div>
            <div class="sub">Min target: 2:1</div>
          </div>
          <div class="ee-block">
            <h4>Position Size</h4>
            <div class="val">${d.position_size}</div>
            <div class="sub">of portfolio</div>
          </div>
        </div>

        <div class="alert-box"><strong>Alert Trigger:</strong> ${d.alert}</div>
        <div class="thesis-box">
          <h4>Thesis</h4>
          <p>${d.thesis}</p>
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
    dr.style.display = 'none'; sr.classList.remove('expanded'); expandedRow = null;
  } else {
    if (expandedRow !== null) {
      document.getElementById('detail-' + expandedRow).style.display = 'none';
      document.getElementById('row-' + expandedRow).classList.remove('expanded');
    }
    dr.style.display = 'table-row'; sr.classList.add('expanded'); expandedRow = idx;
  }
}

function filterAndRender() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  const signal = document.getElementById('signalFilter').value;
  const lynch = document.getElementById('lynchFilter').value;
  const vol = document.getElementById('volFilter').value;
  const market = document.getElementById('marketFilter').value;
  const type = document.getElementById('typeFilter').value;
  expandedRow = null;
  let filtered = allData.filter(d => {
    return (!search || d.ticker.toLowerCase().includes(search) || d.name.toLowerCase().includes(search))
      && (!signal || d.signal_class === signal)
      && (!lynch || d.lynch_cat === lynch)
      && (!vol || (d.vol_label || '').includes(vol))
      && (!market || (market === 'ca' ? d.ticker.endsWith('.TO') : !d.ticker.endsWith('.TO')))
      && (!type || (type === 'etf' ? d.is_etf : !d.is_etf));
  });
  filtered = [...filtered].sort((a, b) => {
    const av = a[sortKey] ?? 0, bv = b[sortKey] ?? 0;
    if (av == null) return 1; if (bv == null) return -1;
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
['signalFilter','lynchFilter','volFilter','marketFilter','typeFilter'].forEach(id => {
  document.getElementById(id).addEventListener('change', filterAndRender);
});

filterAndRender();
</script>
</body>
</html>"""


# ─── EMAIL GENERATOR ─────────────────────────────────────────────────────────

def generate_email_html(results, updated):
    """
    Build an HTML email showing actionable signals only:
    all Strong Buys + Buys with R:R >= 2.0, sorted by composite score.
    """
    actionable = [
        r for r in results
        if r["signal"] == "Strong Buy"
        or (r["signal"] == "Buy" and r["rr"] >= 2.0)
    ]
    actionable.sort(key=lambda x: -x["composite"])

    now_et = datetime.now(ZoneInfo("America/New_York"))
    period = "Morning Open" if now_et.hour < 14 else "Afternoon Close"
    subject_date = now_et.strftime("%B %d, %Y")

    def row_color(signal):
        return "#d4edda" if signal == "Strong Buy" else "#ddefd6"

    def peg_color(peg):
        if peg is None:
            return "#5c4a35"
        return "#2d5a27" if peg < 1 else "#7a2020" if peg > 2 else "#6b5400"

    rows_html = ""
    if not actionable:
        rows_html = """
        <tr><td colspan="8" style="padding:24px;text-align:center;color:#8a7560;
            font-family:Georgia,serif;font-size:14px;">
            No actionable signals at this scan. Market conditions are mixed — patience is a position.
        </td></tr>"""
    else:
        for r in actionable:
            bg = row_color(r["signal"])
            peg_str = f'<span style="color:{peg_color(r["peg"])}">{r["peg"]:.2f}</span>' if r["peg"] else "—"
            ytd_color = "#2d5a27" if r["ytd"] >= 0 else "#7a2020"
            ytd_str = f'{"+" if r["ytd"]>=0 else ""}{r["ytd"]:.1f}%'
            vol_arrow = "▲" if "Accum" in (r["vol_label"] or "") else "▼" if "Distrib" in (r["vol_label"] or "") else "–"
            rr_color = "#2d5a27" if r["rr"] >= 2 else "#6b5400"

            rows_html += f"""
            <tr style="background:{bg};border-bottom:1px solid #d4c9b8;">
              <td style="padding:10px 12px;font-family:'Courier New',monospace;font-size:13px;font-weight:bold;color:#1a1008;white-space:nowrap;">
                {r['ticker']}
              </td>
              <td style="padding:10px 12px;font-family:Georgia,serif;font-size:12px;color:#2c2419;max-width:160px;">
                {r['name']}
              </td>
              <td style="padding:10px 12px;text-align:center;">
                <span style="display:inline-block;padding:2px 8px;border-radius:3px;
                  background:{'#d4edda' if r['signal']=='Strong Buy' else '#ddefd6'};
                  color:{'#1a4a1a' if r['signal']=='Strong Buy' else '#2d5a27'};
                  border:1px solid {'#b8d9c0' if r['signal']=='Strong Buy' else '#c4ddb8'};
                  font-family:'Courier New',monospace;font-size:10px;font-weight:bold;">
                  {r['signal']}
                </span>
              </td>
              <td style="padding:10px 12px;font-family:'Courier New',monospace;font-size:12px;color:#1a1008;white-space:nowrap;">
                $<b>{r['price']:.2f}</b><br>
                <span style="color:#5c4a35;font-size:11px;">Entry: ${r['entry_low']:.2f}–${r['entry_high']:.2f}</span>
              </td>
              <td style="padding:10px 12px;font-family:'Courier New',monospace;font-size:11px;white-space:nowrap;">
                <span style="color:#7a2020;">Stop: ${r['stop']:.2f}</span><br>
                <span style="color:#2d5a27;">T1: ${r['t1']:.2f} / T2: ${r['t2']:.2f}</span>
              </td>
              <td style="padding:10px 12px;font-family:'Courier New',monospace;font-size:12px;
                color:{rr_color};font-weight:bold;text-align:center;">
                {r['rr']:.1f}:1
              </td>
              <td style="padding:10px 12px;font-size:11px;color:#5c4a35;white-space:nowrap;">
                {r.get('lynch_cat','—')}<br>
                PEG: {peg_str}<br>
                <span style="color:{ytd_color};">YTD {ytd_str}</span>
              </td>
              <td style="padding:10px 12px;font-size:11px;color:#5c4a35;">
                {vol_arrow} {r.get('vol_label','—')}<br>
                <span style="color:#2c2419;">{r.get('obv_signal','')[:40]}</span>
              </td>
            </tr>
            <tr style="background:#faf7f1;border-bottom:2px solid #d4c9b8;">
              <td colspan="8" style="padding:8px 12px 12px 12px;font-family:Georgia,serif;
                font-size:12px;color:#2c2419;line-height:1.6;">
                <b style="color:#5c4a35;">Alert:</b> {r['alert']}<br>
                <b style="color:#5c4a35;">Thesis:</b> {r['thesis']}
              </td>
            </tr>"""

    strong_buy_count = sum(1 for r in actionable if r["signal"] == "Strong Buy")
    buy_count = len(actionable) - strong_buy_count

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4efe6;font-family:Georgia,serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4efe6;">
<tr><td align="center" style="padding:24px 16px;">
<table width="700" cellpadding="0" cellspacing="0" style="background:#faf7f1;border:1px solid #d4c9b8;border-radius:6px;overflow:hidden;">

  <!-- Header -->
  <tr style="background:#1a1008;">
    <td style="padding:20px 28px;">
      <div style="font-family:Georgia,serif;font-size:20px;font-weight:bold;color:#f4efe6;">
        Market Scanner
      </div>
      <div style="font-family:'Courier New',monospace;font-size:12px;color:#8a7560;margin-top:4px;">
        {period} &nbsp;|&nbsp; {subject_date} &nbsp;|&nbsp; Technical + Volume + Lynch
      </div>
    </td>
    <td style="padding:20px 28px;text-align:right;vertical-align:middle;">
      <div style="font-family:'Courier New',monospace;font-size:11px;color:#5c4a35;">
        <span style="color:#d4edda;">{strong_buy_count} Strong Buy</span> &nbsp;
        <span style="color:#c4ddb8;">{buy_count} Buy</span>
      </div>
    </td>
  </tr>

  <!-- Summary bar -->
  <tr style="background:#ede8de;border-bottom:1px solid #d4c9b8;">
    <td colspan="2" style="padding:10px 28px;font-family:'Courier New',monospace;font-size:11px;color:#5c4a35;">
      Showing {len(actionable)} actionable signals &nbsp;|&nbsp;
      Strong Buys + Buys with R:R &ge; 2.0 &nbsp;|&nbsp;
      Sorted by composite score &nbsp;|&nbsp;
      Click entry prices to verify on your broker before trading
    </td>
  </tr>

  <!-- Main table -->
  <tr><td colspan="2" style="padding:0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr style="background:#ede8de;">
        <th style="padding:8px 12px;text-align:left;font-family:'Courier New',monospace;font-size:10px;color:#5c4a35;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid #d4c9b8;">Ticker</th>
        <th style="padding:8px 12px;text-align:left;font-family:'Courier New',monospace;font-size:10px;color:#5c4a35;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid #d4c9b8;">Name</th>
        <th style="padding:8px 12px;text-align:left;font-family:'Courier New',monospace;font-size:10px;color:#5c4a35;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid #d4c9b8;">Signal</th>
        <th style="padding:8px 12px;text-align:left;font-family:'Courier New',monospace;font-size:10px;color:#5c4a35;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid #d4c9b8;">Price / Entry</th>
        <th style="padding:8px 12px;text-align:left;font-family:'Courier New',monospace;font-size:10px;color:#5c4a35;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid #d4c9b8;">Stop / Targets</th>
        <th style="padding:8px 12px;text-align:center;font-family:'Courier New',monospace;font-size:10px;color:#5c4a35;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid #d4c9b8;">R:R</th>
        <th style="padding:8px 12px;text-align:left;font-family:'Courier New',monospace;font-size:10px;color:#5c4a35;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid #d4c9b8;">Lynch / PEG</th>
        <th style="padding:8px 12px;text-align:left;font-family:'Courier New',monospace;font-size:10px;color:#5c4a35;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid #d4c9b8;">Volume</th>
      </tr>
      {rows_html}
    </table>
  </td></tr>

  <!-- R:R explainer -->
  <tr style="background:#ede8de;border-top:2px solid #d4c9b8;">
    <td colspan="2" style="padding:14px 28px;">
      <div style="font-family:Georgia,serif;font-size:12px;color:#5c4a35;line-height:1.6;">
        <b>R:R (Risk to Reward)</b> — A 2:1 ratio means you risk $1 to potentially make $2.
        Only trade setups with R:R &ge; 2:1. Below that, the math doesn't justify the risk
        regardless of how strong the thesis sounds. Position size shown is % of total portfolio.
      </div>
    </td>
  </tr>

  <!-- Footer -->
  <tr style="background:#1a1008;">
    <td colspan="2" style="padding:14px 28px;font-family:'Courier New',monospace;font-size:10px;color:#5c4a35;line-height:1.6;">
      Not financial advice. All signals are algorithmic estimates. Always do your own due diligence before trading.
      Data: Yahoo Finance. Full dashboard: https://gtmautomationops-dev.github.io/market-scanner/
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    return html, f"Market Scanner — {period} Signals — {subject_date}"


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
