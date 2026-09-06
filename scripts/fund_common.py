#!/usr/bin/env python3
"""
fund_common — shared plumbing for the micro hedge-fund agents.

Three named agents run off this module, in the spirit of the WSJ "kitchen-table
hedge fund" piece:

  * Alex  (scripts/analyst_alex.py) — scans the market for promising stocks/ETFs
  * Sarah (scripts/risk_sarah.py)   — checks open positions before the close
  * Elena (scripts/report_elena.py) — writes the weekly performance report

They are ADVISORY. Nothing here places an order. There are two "books":

  1. My Picks — the book YOU control. You record real (or tracked) lots in
     config/my_picks.yml. The agents mark them to market, risk-check them, and
     report on them. They never edit that file.
  2. Momentum — the existing paper (simulated) portfolio managed automatically
     by scripts/momentum_trader.py, read straight from data/momentum_trader.db.

This module holds the pieces all three agents share so they never drift: config
loading, price fetching (reusing the momentum trader's battle-tested batch
downloader), marking each book to market, the risk-flag rules Sarah applies, the
daily equity snapshot both Sarah and Elena persist, and the common dark-theme
dashboard chrome so the three pages read as one family.

The pure logic (marking, flagging, aggregating) takes prices/holdings as plain
arguments so it can be unit-tested offline with synthetic data — no network.

Not financial advice. Educational tooling over public price data.
"""

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
DOCS = ROOT / "docs"
ET = ZoneInfo("America/New_York")

FUND_DB = DATA / "hedge_fund.db"
MOMENTUM_DB = DATA / "momentum_trader.db"
MY_PICKS_PATH = CONFIG / "my_picks.yml"

BASE_URL = "https://gtmautomationops-dev.github.io/market-scanner"

DISCLAIMER = (
    "Not financial advice. These agents are advisory: they analyze public price "
    "data and flag ideas and risks — they never place orders. The Momentum book "
    "is a paper (simulated) portfolio; the My Picks book is whatever you record "
    "in config/my_picks.yml. Prices are delayed and marks use daily closes, "
    "ignoring slippage, spreads, and fees. Do your own due diligence."
)


# ─── CONFIG / HOLDINGS ────────────────────────────────────────────────────────

def load_yaml(path, default=None):
    p = Path(path)
    if not p.exists():
        return {} if default is None else default
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or ({} if default is None else default)


def _f(v, dflt=None):
    """Best-effort float coercion; returns dflt on None/blank/bad input."""
    if v is None or v == "":
        return dflt
    try:
        return float(v)
    except (TypeError, ValueError):
        return dflt


def _norm_lot(lot):
    """Normalize one holdings entry into a predictable dict."""
    return {
        "symbol": str(lot.get("symbol", "")).strip().upper(),
        "shares": _f(lot.get("shares"), 0.0) or 0.0,
        "entry_price": _f(lot.get("entry_price")),
        "entry_date": str(lot.get("entry_date", "")).strip() or None,
        "exit_price": _f(lot.get("exit_price")),
        "exit_date": str(lot.get("exit_date", "")).strip() or None,
        "stop": _f(lot.get("stop")),
        "target": _f(lot.get("target")),
        "note": str(lot.get("note", "")).strip(),
    }


def load_holdings(path=MY_PICKS_PATH):
    """
    Read config/my_picks.yml → {benchmark, open:[lot...], closed:[lot...]}.
    Only well-formed lots (a symbol, positive shares, an entry price) survive so a
    half-typed row can never crash an agent mid-run.
    """
    cfg = load_yaml(path, {})
    benchmark = str(cfg.get("benchmark", "SPY")).strip().upper() or "SPY"
    raw_open = cfg.get("holdings") or []
    raw_closed = cfg.get("closed") or []

    open_lots, closed_lots = [], []
    for lot in raw_open:
        n = _norm_lot(lot)
        if n["symbol"] and n["shares"] > 0 and n["entry_price"]:
            open_lots.append(n)
    for lot in raw_closed:
        n = _norm_lot(lot)
        if n["symbol"] and n["shares"] > 0 and n["entry_price"] and n["exit_price"]:
            closed_lots.append(n)
    return {"benchmark": benchmark, "open": open_lots, "closed": closed_lots}


def held_symbols(my_book, momentum_book):
    """Every symbol currently held across both books (for Alex to skip/annotate)."""
    syms = {p["symbol"] for p in (my_book or {}).get("positions", [])}
    if momentum_book:
        syms |= {p["symbol"] for p in momentum_book.get("positions", [])}
    return syms


# ─── PRICING ──────────────────────────────────────────────────────────────────

def fetch_prices(tickers):
    """
    Batch-download daily history → {ticker: (closes, volumes)}.
    Reuses the momentum trader's downloader so the two tools share one code path.
    """
    from momentum_trader import fetch_history  # lazy: avoids heavy import for tests
    uniq = [t for t in dict.fromkeys(t for t in tickers if t)]
    if not uniq:
        return {}
    return fetch_history(uniq)


def last_price(prices, ticker, fallback=None):
    data = prices.get(ticker)
    if data and data[0]:
        return data[0][-1]
    return fallback


def days_held(entry_date, today=None):
    """Calendar days from an ISO entry_date to today; None if unparseable."""
    if not entry_date:
        return None
    try:
        d0 = date.fromisoformat(str(entry_date)[:10])
    except ValueError:
        return None
    t = today or datetime.now(ET).date()
    return (t - d0).days


# ─── MY PICKS BOOK ────────────────────────────────────────────────────────────

def mark_my_picks(holdings, prices, today=None):
    """
    Mark the user-controlled book to market. Pure: pass a `prices` dict
    ({ticker: (closes, volumes)}) so this is unit-testable offline.

    Returns a dict with per-lot rows and book totals. Open lots without a live
    price fall back to their entry price (marked flat) rather than vanishing.
    """
    today = today or datetime.now(ET).date()
    positions, cost_basis, market_value = [], 0.0, 0.0

    for lot in holdings.get("open", []):
        px = last_price(prices, lot["symbol"], lot["entry_price"])
        priced = prices.get(lot["symbol"]) is not None
        shares, entry = lot["shares"], lot["entry_price"]
        cost = entry * shares
        mv = px * shares
        unreal = mv - cost
        unreal_pct = (px / entry - 1) * 100 if entry else 0.0
        risk = (entry - lot["stop"]) if lot["stop"] else None
        r_now = (px - entry) / risk if risk and risk > 0 else None
        cost_basis += cost
        market_value += mv
        positions.append({
            "symbol": lot["symbol"], "shares": shares, "entry": entry,
            "entry_date": lot["entry_date"], "price": round(px, 2), "priced": priced,
            "cost": round(cost, 2), "mv": round(mv, 2),
            "unreal": round(unreal, 2), "unreal_pct": round(unreal_pct, 2),
            "stop": lot["stop"], "target": lot["target"], "r_now": r_now,
            "days_held": days_held(lot["entry_date"], today), "note": lot["note"],
            "book": "My Picks",
        })

    realized = 0.0
    closed = []
    for lot in holdings.get("closed", []):
        pnl = (lot["exit_price"] - lot["entry_price"]) * lot["shares"]
        pnl_pct = (lot["exit_price"] / lot["entry_price"] - 1) * 100 if lot["entry_price"] else 0.0
        realized += pnl
        closed.append({
            "symbol": lot["symbol"], "shares": lot["shares"], "entry": lot["entry_price"],
            "exit": lot["exit_price"], "entry_date": lot["entry_date"],
            "exit_date": lot["exit_date"], "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
            "book": "My Picks",
        })

    unrealized = market_value - cost_basis
    return {
        "positions": positions, "closed": closed,
        "cost_basis": round(cost_basis, 2), "market_value": round(market_value, 2),
        "unrealized": round(unrealized, 2), "realized": round(realized, 2),
        "total_pnl": round(unrealized + realized, 2),
        "return_pct": round(unrealized / cost_basis * 100, 2) if cost_basis else 0.0,
        "n_open": len(positions), "n_closed": len(closed),
    }


# ─── MOMENTUM BOOK (read-only view of momentum_trader.db) ─────────────────────

def read_momentum_book(prices, db_path=MOMENTUM_DB):
    """
    Read the paper portfolio managed by momentum_trader.py and mark it to market
    with the same live prices. Returns None if the ledger doesn't exist yet.
    """
    p = Path(db_path)
    if not p.exists():
        return None
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    try:
        acct = con.execute("SELECT * FROM account WHERE id = 1").fetchone()
        if acct is None:
            return None
        starting, cash = acct["starting_cash"], acct["cash"]

        positions, positions_value = [], 0.0
        for pos in con.execute("SELECT * FROM positions ORDER BY entry_date").fetchall():
            px = last_price(prices, pos["symbol"], pos["last_price"] or pos["entry_price"])
            priced = prices.get(pos["symbol"]) is not None
            shares, entry = pos["shares"], pos["entry_price"]
            mv = px * shares
            positions_value += mv
            unreal = (px - entry) * shares
            unreal_pct = (px / entry - 1) * 100 if entry else 0.0
            risk = entry - pos["initial_stop"]
            r_now = (px - entry) / risk if risk and risk > 0 else None
            positions.append({
                "symbol": pos["symbol"], "name": pos["name"], "shares": shares,
                "entry": entry, "entry_date": pos["entry_date"], "price": round(px, 2),
                "priced": priced, "mv": round(mv, 2), "unreal": round(unreal, 2),
                "unreal_pct": round(unreal_pct, 2), "stop": pos["stop"],
                "target": pos["target"], "r_now": r_now, "armed": bool(pos["armed"]),
                "days_held": days_held(pos["entry_date"]),
                "score": pos["score"], "book": "Momentum",
            })

        trades = [dict(r) for r in con.execute(
            "SELECT * FROM trades ORDER BY exit_date DESC, id DESC").fetchall()]
        curve = [dict(r) for r in con.execute(
            "SELECT snap_date, total_equity, benchmark_price FROM equity "
            "ORDER BY snap_date").fetchall()]
    finally:
        con.close()

    total_equity = cash + positions_value
    return {
        "starting": starting, "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total_equity": round(total_equity, 2),
        "total_pnl": round(total_equity - starting, 2),
        "return_pct": round((total_equity / starting - 1) * 100, 2) if starting else 0.0,
        "positions": positions, "trades": trades, "curve": curve,
        "n_open": len(positions), "n_closed": len(trades),
    }


# ─── RISK RULES (Sarah's brain — pure, testable) ──────────────────────────────

def position_flags(pos, cfg):
    """
    Evaluate one open position against Sarah's thresholds. Returns a list of
    {level, code, msg}; level is 'alert' (act now) or 'watch' (keep an eye on).
    Works for a position dict from either book.
    """
    flags = []
    px = pos["price"]
    stop, target = pos.get("stop"), pos.get("target")
    near_stop = _f(cfg.get("near_stop_pct"), 3.0) / 100
    near_target = _f(cfg.get("near_target_pct"), 3.0) / 100
    loss_alert = _f(cfg.get("loss_alert_pct"), 12.0)
    stale_days = _f(cfg.get("stale_days"), 30)
    stale_band = _f(cfg.get("stale_flat_band"), 5.0)

    if stop:
        if px <= stop:
            flags.append({"level": "alert", "code": "stop_breached",
                          "msg": f"below stop ${stop:.2f} (last ${px:.2f}) — exit trigger"})
        elif px <= stop * (1 + near_stop):
            gap = (px / stop - 1) * 100
            flags.append({"level": "watch", "code": "near_stop",
                          "msg": f"{gap:.1f}% above stop ${stop:.2f} — tighten or be ready"})
    if target:
        if px >= target:
            flags.append({"level": "alert", "code": "target_hit",
                          "msg": f"at/over target ${target:.2f} — consider trimming"})
        elif px >= target * (1 - near_target):
            gap = (target / px - 1) * 100
            flags.append({"level": "watch", "code": "near_target",
                          "msg": f"{gap:.1f}% from target ${target:.2f}"})

    if pos["unreal_pct"] <= -loss_alert:
        flags.append({"level": "alert", "code": "big_loss",
                      "msg": f"down {pos['unreal_pct']:.1f}% — review thesis"})

    dh = pos.get("days_held")
    if dh is not None and dh >= stale_days and abs(pos["unreal_pct"]) < stale_band:
        flags.append({"level": "watch", "code": "stale",
                      "msg": f"flat ({pos['unreal_pct']:+.1f}%) after {dh}d — dead money?"})
    return flags


def concentration_flags(positions, total_value, cfg):
    """Flag any single position that is an outsized share of total book value."""
    limit = _f(cfg.get("concentration_pct"), 25.0)
    out = []
    if not total_value or total_value <= 0:
        return out
    for p in positions:
        w = p["mv"] / total_value * 100
        if w >= limit:
            out.append({"symbol": p["symbol"], "weight": round(w, 1),
                        "level": "watch", "code": "concentration",
                        "msg": f"{w:.0f}% of book — concentrated"})
    return out


def drawdown_from_peak(curve_values):
    """Current drawdown (%) from the running peak of an equity series."""
    peak, cur = None, None
    for v in curve_values:
        if v is None:
            continue
        cur = v
        peak = v if peak is None else max(peak, v)
    if not peak or cur is None:
        return 0.0
    return round((cur - peak) / peak * 100, 2)


# ─── HEDGE-FUND DB (daily snapshot for the My Picks book) ─────────────────────

def _fund_connect():
    DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(FUND_DB)
    con.row_factory = sqlite3.Row
    con.execute(
        """CREATE TABLE IF NOT EXISTS my_picks_equity (
               snap_date       TEXT PRIMARY KEY,
               cost_basis      REAL,
               market_value    REAL,
               unrealized      REAL,
               realized        REAL,
               total_pnl       REAL,
               benchmark_price REAL
           )"""
    )
    con.commit()
    return con


def snapshot_my_picks(my_book, benchmark_price, today=None):
    """Upsert today's My Picks P&L snapshot so Elena has a weekly history to plot."""
    today = (today or datetime.now(ET).date()).isoformat() if not isinstance(today, str) else today
    con = _fund_connect()
    try:
        con.execute(
            """INSERT INTO my_picks_equity
                 (snap_date, cost_basis, market_value, unrealized, realized, total_pnl, benchmark_price)
                 VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(snap_date) DO UPDATE SET
                 cost_basis=excluded.cost_basis, market_value=excluded.market_value,
                 unrealized=excluded.unrealized, realized=excluded.realized,
                 total_pnl=excluded.total_pnl, benchmark_price=excluded.benchmark_price""",
            (today, my_book["cost_basis"], my_book["market_value"], my_book["unrealized"],
             my_book["realized"], my_book["total_pnl"],
             round(benchmark_price, 2) if benchmark_price else None),
        )
        con.commit()
    finally:
        con.close()


def my_picks_curve():
    """Historical My Picks snapshots for the weekly report (oldest first)."""
    if not FUND_DB.exists():
        return []
    con = _fund_connect()
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM my_picks_equity ORDER BY snap_date").fetchall()]
    finally:
        con.close()


# ─── SHARED DASHBOARD CHROME ──────────────────────────────────────────────────

AGENTS = [
    ("Alex",  "analyst_alex.html",   "Analyst"),
    ("Sarah", "risk_sarah.html",     "Risk"),
    ("Elena", "report_elena.html",   "Report"),
]
OTHER_LINKS = [
    ("Momentum", "momentum_trader.html"),
    ("Scanner",  "index.html"),
]

SHARED_CSS = """
  * { box-sizing:border-box; }
  body { margin:0; background:#0b0f17; color:#e5e7eb;
         font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }
  a { color:#93c5fd; text-decoration:none; }
  .wrap { max-width:1040px; margin:0 auto; padding:20px 16px 64px; }
  .nav { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:18px; }
  .nav a { background:#111827; border:1px solid #1f2937; border-radius:999px;
           padding:5px 13px; font-size:13px; color:#cbd5e1; }
  .nav a.on { background:#1e293b; color:#93c5fd; border-color:#334155; }
  .nav a.alt { color:#64748b; }
  h1 { font-size:24px; margin:0 0 4px; }
  .who { color:#94a3b8; font-size:13.5px; margin:0 0 6px; }
  .meta { color:#64748b; font-size:12.5px; margin-bottom:20px; }
  .pill { display:inline-block; background:#1e293b; color:#93c5fd; border-radius:999px;
          padding:2px 10px; font-size:12px; margin-left:6px;
          text-transform:uppercase; letter-spacing:.04em; }
  .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
           gap:12px; margin-bottom:20px; }
  .stat { background:#111827; border:1px solid #1f2937; border-radius:12px; padding:14px 16px; }
  .stat .lbl { color:#94a3b8; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  .stat .val { font-size:22px; font-weight:700; margin-top:4px; }
  .stat .sub { color:#64748b; font-size:12px; }
  h2 { font-size:15px; text-transform:uppercase; letter-spacing:.05em; color:#94a3b8;
       margin:26px 0 10px; }
  .card { background:#111827; border:1px solid #1f2937; border-radius:12px;
          padding:6px 4px; overflow-x:auto; }
  table { width:100%; border-collapse:collapse; font-size:13.5px; }
  th { text-align:left; color:#64748b; font-weight:600; font-size:11px;
       text-transform:uppercase; letter-spacing:.04em; padding:8px 10px;
       border-bottom:1px solid #1f2937; }
  td { padding:9px 10px; border-bottom:1px solid #161e2e; vertical-align:top; }
  tr:last-child td { border-bottom:none; }
  .sub { color:#64748b; font-size:11.5px; }
  .empty { color:#64748b; text-align:center; padding:20px; }
  .tag { font-size:11px; font-weight:700; letter-spacing:.05em; border-radius:6px;
         padding:2px 8px; margin-right:6px; }
  .tag.alert { background:#7f1d1d; color:#fecaca; }
  .tag.watch { background:#78350f; color:#fde68a; }
  .tag.ok { background:#14532d; color:#bbf7d0; }
  .tag.book { background:#312e81; color:#c7d2fe; }
  .banner { border-radius:12px; padding:13px 16px; margin-bottom:18px; font-size:14.5px; }
  .banner.alert { background:#3f1d1d; border:1px solid #7f1d1d; }
  .banner.calm { background:#12261c; border:1px solid #166534; }
  .banner.flat { background:#1f2937; border:1px solid #374151; color:#cbd5e1; }
  .disc { color:#64748b; font-size:12px; margin-top:34px; border-top:1px solid #1f2937;
          padding-top:16px; }
  .pos { color:#22c55e; } .neg { color:#ef4444; }
"""


def money(v):
    return f"${v:,.0f}" if v is not None else "—"


def pct(v, signed=True):
    if v is None:
        return "—"
    return f"{v:+.1f}%" if signed else f"{v:.1f}%"


def color_of(v):
    return "pos" if (v or 0) >= 0 else "neg"


def nav_html(active_file):
    items = []
    for _name, fn, _role in AGENTS:
        cls = "on" if fn == active_file else ""
        items.append(f'<a class="{cls}" href="{fn}">{_name} · {_role}</a>')
    for _name, fn in OTHER_LINKS:
        items.append(f'<a class="alt" href="{fn}">{_name}</a>')
    return '<div class="nav">' + "".join(items) + "</div>"


def page(title, agent_file, who, updated, body):
    """Assemble a full dashboard page with shared chrome."""
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{SHARED_CSS}</style></head><body><div class="wrap">
{nav_html(agent_file)}
<h1>{title}</h1>
<div class="who">{who}</div>
<div class="meta">Updated {updated}</div>
{body}
<div class="disc"><b>Not financial advice.</b> {DISCLAIMER}</div>
</div></body></html>"""


def write_agent_outputs(agent_slug, dashboard_html, email_html, subject):
    """Write the trio's standard output set for a given agent."""
    DOCS.mkdir(exist_ok=True)
    (DOCS / f"{agent_slug}.html").write_text(dashboard_html, encoding="utf-8")
    (DOCS / f"{agent_slug}_email.html").write_text(email_html, encoding="utf-8")
    (DOCS / f"{agent_slug}_email_subject.txt").write_text(subject, encoding="utf-8")


def write_runlog(agent_slug, payload):
    DATA.mkdir(exist_ok=True)
    payload = {"run_at": datetime.now(timezone.utc).isoformat(), **payload}
    (DATA / f"{agent_slug}_runlog.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")


def now_et_str():
    return datetime.now(ET).strftime("%B %d, %Y at %H:%M ET")


# Shared email skeleton (light theme, matches the rest of the repo's emails).
def email_shell(heading, badge, updated, inner, footer_link):
    return f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:620px;
      margin:0 auto;color:#0f172a">
      <h2 style="margin:0 0 2px">{heading}
        <span style="font-size:12px;background:#e2e8f0;border-radius:6px;padding:2px 8px;
          text-transform:uppercase;letter-spacing:.04em">{badge}</span></h2>
      <p style="color:#64748b;margin:0 0 16px;font-size:13px">Updated {updated}</p>
      {inner}
      <p style="color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0;padding-top:12px">
        Advisory only — not financial advice. Marks use daily closes, ignoring slippage and
        fees. <a href="{footer_link}">Full dashboard →</a></p>
    </div>"""
