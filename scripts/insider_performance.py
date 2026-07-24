"""Insider Radar signal quality: opportunistic-vs-routine insider timing and a
forward-return scorecard that measures our bullish signals against SPY.

Two evidence-oriented additions toward the goal of an actual edge:

1. Opportunistic vs routine (Cohen, Malloy, Pomorski 2012): insiders who trade
   on the SAME calendar month every year ("routine" — scheduled comp) carried
   no predictive power; off-schedule ("opportunistic") insiders did. We tag the
   flagged conviction buyers so routine ones can be de-emphasised.

2. Hit-rate scorecard: every conviction signal is recorded with its entry
   price, then graded by forward return vs SPY. This is the accountability
   mechanism — it tells you with real numbers whether the signals beat the
   index, rather than assuming they do. Early samples are small; treat as
   provisional.
"""

import sqlite3
from datetime import datetime, timezone

import requests

PERF_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_history (
    accession TEXT NOT NULL,
    ticker TEXT NOT NULL,
    filing_date TEXT,
    insider_cik TEXT,
    insider_name TEXT,
    signal TEXT,
    entry_price REAL,
    insider_timing TEXT,
    recorded_at TEXT,
    PRIMARY KEY (accession, ticker)
);
"""

CONVICTION = ("STRONG BULLISH", "BULLISH")
_UA = "MarketScanner InsiderRadar devrim.birlik@revunited.ca"


def ensure_perf_tables(conn):
    conn.executescript(PERF_SCHEMA)


# ---------------------------------------------------------------- timing

def classify_insider_timing(insider_cik, tx_date, session, cache):
    """routine | opportunistic | unknown, from the insider's EDGAR filing
    history. Routine = files Form 4 in the same calendar month in 2+ prior
    years (a scheduled, comp-driven pattern with no predictive content)."""
    if not insider_cik:
        return "unknown"
    if insider_cik in cache:
        return cache[insider_cik]
    result = "unknown"
    try:
        r = session.get(
            f"https://data.sec.gov/submissions/CIK{insider_cik}.json", timeout=20
        )
        if r.ok:
            recent = r.json().get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            tx_year, tx_month = int(tx_date[:4]), int(tx_date[5:7])
            years_same_month = set()
            for f, d in zip(forms, dates):
                if f in ("4", "4/A") and len(d) >= 7:
                    y, m = int(d[:4]), int(d[5:7])
                    if m == tx_month and y < tx_year:
                        years_same_month.add(y)
            result = "routine" if len(years_same_month) >= 2 else "opportunistic"
    except Exception:
        pass
    cache[insider_cik] = result
    return result


# ---------------------------------------------------------------- prices

def _price_frames(tickers):
    """{ticker: [(date, close), ...]} ascending, via one yfinance batch."""
    tickers = sorted({t for t in tickers if t} | {"SPY"})
    frames = {}
    try:
        import yfinance as yf
        data = yf.download(" ".join(tickers), period="1y", auto_adjust=True,
                           progress=False, threads=True, group_by="ticker")
        multi = len(tickers) > 1
        for t in tickers:
            try:
                hist = data[t] if multi else data
                if multi and t not in data.columns.get_level_values(0):
                    continue
                closes = hist["Close"].dropna()
                frames[t] = [(idx.date().isoformat(), float(v)) for idx, v in closes.items()]
            except Exception:
                continue
    except Exception:
        pass
    return frames


def _close_on_or_after(frame, date_iso):
    for d, c in frame:
        if d >= date_iso:
            return c
    return None


def _latest_close(frame):
    return frame[-1][1] if frame else None


# ---------------------------------------------------------------- scorecard

def update_and_score(conn, cfg, rows, session=None):
    """Record today's conviction signals (with entry price + insider timing),
    then grade every recorded signal by forward return vs SPY.

    Returns {"scorecard": {...}, "timing": {accession: routine|opportunistic}}.
    """
    ensure_perf_tables(conn)
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", _UA)
    cur = conn.cursor()

    conviction_rows = [r for r in rows if r["signal"] in CONVICTION and r["ticker"]]

    # Tickers we need prices for: new conviction rows + everything tracked.
    cur.execute("SELECT DISTINCT ticker FROM signal_history")
    tracked = {r[0] for r in cur.fetchall()}
    frames = _price_frames({r["ticker"] for r in conviction_rows} | tracked)

    # --- record new signals + classify insider timing
    timing_cache, timing_by_acc = {}, {}
    for r in conviction_rows:
        timing = classify_insider_timing(r.get("insider_cik"), r["filed_at"], session, timing_cache)
        timing_by_acc[r["accession"]] = timing
        frame = frames.get(r["ticker"])
        entry = _close_on_or_after(frame, r["filed_at"]) if frame else None
        cur.execute(
            """INSERT OR IGNORE INTO signal_history
               (accession, ticker, filing_date, insider_cik, insider_name,
                signal, entry_price, insider_timing, recorded_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (r["accession"], r["ticker"], r["filed_at"], r.get("insider_cik"),
             r.get("insider"), r["signal"], entry, timing,
             datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()

    # --- grade every recorded signal with a known entry price
    min_age = cfg.get("performance", {}).get("min_grade_age_days", 21)
    today = datetime.now(timezone.utc).date()
    spy_frame = frames.get("SPY", [])
    spy_now = _latest_close(spy_frame)

    graded, excesses, wins, by_timing = 0, [], 0, {"opportunistic": [], "routine": [], "unknown": []}
    cur.execute(
        "SELECT ticker, filing_date, entry_price, insider_timing FROM signal_history "
        "WHERE entry_price IS NOT NULL"
    )
    for ticker, filing_date, entry, timing in cur.fetchall():
        try:
            age = (today - datetime.strptime(filing_date, "%Y-%m-%d").date()).days
        except Exception:
            continue
        if age < min_age:
            continue
        frame = frames.get(ticker)
        now = _latest_close(frame) if frame else None
        spy_entry = _close_on_or_after(spy_frame, filing_date)
        if not (now and entry and spy_entry and spy_now):
            continue
        tick_ret = now / entry - 1
        spy_ret = spy_now / spy_entry - 1
        excess = tick_ret - spy_ret
        graded += 1
        excesses.append(excess)
        wins += 1 if excess > 0 else 0
        by_timing.setdefault(timing or "unknown", []).append(excess)

    def _avg(xs):
        return sum(xs) / len(xs) if xs else None

    scorecard = {
        "graded": graded,
        "min_age_days": min_age,
        "avg_excess_vs_spy": _avg(excesses),
        "beat_spy_pct": (wins / graded) if graded else None,
        "by_timing": {k: {"n": len(v), "avg_excess": _avg(v)} for k, v in by_timing.items() if v},
        "total_tracked": conn.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0],
    }
    return {"scorecard": scorecard, "timing": timing_by_acc}
