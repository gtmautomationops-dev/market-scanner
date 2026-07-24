#!/usr/bin/env python3
"""
Momentum Trader — deterministic, one-pick-per-day PAPER-trading engine.

Rebuild of github.com/merjua14/ai-momentum-trader, adapted to this repo's
signal-and-dashboard architecture:

  * The reference bot places one AI-selected momentum trade per day on
    Robinhood with REAL money. This version is PAPER ONLY. It keeps a
    simulated cash ledger in data/momentum_trader.db — no brokerage, no
    real orders, no API keys.
  * The reference "AI decision layer" is replaced with a transparent,
    reproducible momentum ranking over the same 300+ ticker universe the
    scanner already tracks.
  * Everything else is faithful: at most one entry per calendar day,
    risk-profile position sizing on settled cash, an ATR-based initial stop
    that arms to breakeven and then trails the peak, and a profit target
    expressed in R (multiples of initial risk).

Each run it:
  1. Marks open positions to market and manages trailing stops / targets.
  2. Ranks the universe by momentum.
  3. Enters the top qualifying candidate (once per day) if it has room.
  4. Snapshots equity, then writes:
       docs/momentum_trader.html      — interactive dashboard (GitHub Pages)
       docs/momentum_email.html       — email summary
       docs/momentum_email_subject.txt
       data/momentum_trader.db        — the paper ledger
       data/momentum_trader_runlog.json

Not financial advice. Simulated results ignore slippage, spreads, fees, and
the psychology of trading real money. It is a backtest that happens to run
forward in time.
"""

import json
import sqlite3
import time
from datetime import datetime, date, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
import yfinance as yf

# Reuse the scanner's universe and shared math so the two tools never drift.
from scanner import (
    US_STOCKS, US_ETFS, CA_STOCKS, CA_ETFS,
    calculate_rsi, compute_atr,
)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "momentum_trader.yml"
DB_PATH = ROOT / "data" / "momentum_trader.db"
RUNLOG_PATH = ROOT / "data" / "momentum_trader_runlog.json"
DOCS = ROOT / "docs"
ET = ZoneInfo("America/New_York")

# Daily-reset leveraged / decay ETFs. Trailing-stop math is unreliable on
# products whose exposure resets every session, so we skip them by default.
LEVERAGED = {
    "TQQQ", "SOXL", "UPRO", "EDC", "FAS", "EURL", "DUSL", "BRZU",
    "INDL", "MUU", "KORU", "BITO",
}


# ─── CONFIG ───────────────────────────────────────────────────────────────────

def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    profile_name = cfg.get("risk_profile", "normal")
    profile = cfg["profiles"][profile_name]
    profile["name"] = profile_name
    cfg["profile"] = profile
    return cfg


def build_universe(cfg):
    u = cfg.get("universe", {})
    include_etfs = u.get("include_etfs", True)
    include_canada = u.get("include_canada", True)
    tickers = list(US_STOCKS)
    if include_etfs:
        tickers += US_ETFS
    if include_canada:
        tickers += CA_STOCKS
        if include_etfs:
            tickers += CA_ETFS
    if u.get("exclude_leveraged", True):
        tickers = [t for t in tickers if t not in LEVERAGED]
    # De-dupe, preserve order.
    seen, out = set(), []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ─── DATABASE ─────────────────────────────────────────────────────────────────

def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def db_init(con, cfg):
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS account (
            id            INTEGER PRIMARY KEY CHECK (id = 1),
            starting_cash REAL,
            cash          REAL,
            created_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS positions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol        TEXT,
            name          TEXT,
            entry_date    TEXT,
            entry_price   REAL,
            shares        INTEGER,
            initial_stop  REAL,
            stop          REAL,
            peak          REAL,
            target        REAL,
            armed         INTEGER DEFAULT 0,
            score         REAL,
            risk_profile  TEXT,
            last_price    REAL
        );
        CREATE TABLE IF NOT EXISTS trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol        TEXT,
            name          TEXT,
            entry_date    TEXT,
            entry_price   REAL,
            exit_date     TEXT,
            exit_price    REAL,
            shares        INTEGER,
            pnl           REAL,
            pnl_pct       REAL,
            r_multiple    REAL,
            exit_reason   TEXT,
            risk_profile  TEXT
        );
        CREATE TABLE IF NOT EXISTS equity (
            snap_date        TEXT PRIMARY KEY,
            cash             REAL,
            positions_value  REAL,
            total_equity     REAL,
            benchmark_price  REAL
        );
        CREATE TABLE IF NOT EXISTS picks (
            run_at  TEXT,
            symbol  TEXT,
            action  TEXT,
            note    TEXT
        );
        """
    )
    row = con.execute("SELECT id FROM account WHERE id = 1").fetchone()
    if row is None:
        cash = float(cfg.get("starting_cash", 10000))
        con.execute(
            "INSERT INTO account (id, starting_cash, cash, created_at) VALUES (1, ?, ?, ?)",
            (cash, cash, datetime.now(timezone.utc).isoformat()),
        )
    con.commit()


def get_account(con):
    return con.execute("SELECT * FROM account WHERE id = 1").fetchone()


def set_cash(con, cash):
    con.execute("UPDATE account SET cash = ? WHERE id = 1", (round(cash, 2),))


# ─── MOMENTUM SCORING ─────────────────────────────────────────────────────────

def _sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ret(closes, days):
    """Percent return over `days` trading days, or None if not enough history."""
    if len(closes) > days and closes[-days - 1] > 0:
        return (closes[-1] / closes[-days - 1] - 1) * 100
    return None


def momentum_score(closes, volumes):
    """
    Transparent additive momentum score. Every factor contributes named points
    so the thesis and dashboard can explain *why* a name ranked where it did.
    Returns (score, factors) where factors is a list of "±pts reason" strings.
    """
    if len(closes) < 30:
        return None, []

    current = closes[-1]
    factors = []
    score = 0.0

    def add(pts, reason):
        nonlocal score
        score += pts
        factors.append(f"{'+' if pts >= 0 else ''}{pts:.2f} {reason}")

    # 1. Three-month return — the momentum backbone.
    r3 = _ret(closes, 63)
    if r3 is not None:
        if r3 > 20:      add(2.0, f"3m +{r3:.0f}% (strong)")
        elif r3 > 10:    add(1.5, f"3m +{r3:.0f}%")
        elif r3 > 0:     add(0.75, f"3m +{r3:.0f}%")
        elif r3 > -10:   add(-1.0, f"3m {r3:.0f}%")
        else:            add(-2.0, f"3m {r3:.0f}% (weak)")

    # 2. One-month return — recent acceleration.
    r1 = _ret(closes, 21)
    if r1 is not None:
        if r1 > 10:      add(1.5, f"1m +{r1:.0f}% (accelerating)")
        elif r1 > 3:     add(1.0, f"1m +{r1:.0f}%")
        elif r1 > 0:     add(0.5, f"1m +{r1:.0f}%")
        else:            add(-0.75, f"1m {r1:.0f}%")

    # 3. Six-month return — trend persistence.
    r6 = _ret(closes, 126)
    if r6 is not None:
        if r6 > 30:      add(1.0, f"6m +{r6:.0f}%")
        elif r6 > 0:     add(0.5, f"6m +{r6:.0f}%")
        else:            add(-0.5, f"6m {r6:.0f}%")

    # 4. Position relative to moving averages.
    ma20, ma50, ma200 = _sma(closes, 20), _sma(closes, 50), _sma(closes, 200)
    if ma20 and current > ma20:
        add(0.75, "above 20-day MA")
    if ma50 and current > ma50:
        add(0.75, "above 50-day MA")
    if ma200 and current > ma200:
        add(1.0, "above 200-day MA")
    if ma20 and ma50 and ma200 and ma20 > ma50 > ma200:
        add(1.0, "MAs stacked bullishly")

    # 5. RSI — reward healthy momentum, penalize the extremes.
    rsi = calculate_rsi(closes)
    if 55 <= rsi <= 72:
        add(1.0, f"RSI {rsi:.0f} (healthy)")
    elif 45 <= rsi < 55 or 72 < rsi <= 78:
        add(0.25, f"RSI {rsi:.0f}")
    elif rsi > 80:
        add(-1.0, f"RSI {rsi:.0f} (overbought)")
    elif rsi < 40:
        add(-0.75, f"RSI {rsi:.0f} (no momentum)")

    # 6. Volume expansion — is the move backed by participation?
    vol_ratio = 1.0
    if len(volumes) >= 60:
        v20 = _sma(volumes, 20)
        v60 = _sma(volumes, 60)
        if v60 and v60 > 0:
            vol_ratio = v20 / v60
            if vol_ratio > 1.2:   add(1.0, f"volume +{(vol_ratio - 1) * 100:.0f}%")
            elif vol_ratio > 1.0: add(0.5, "volume rising")
            elif vol_ratio < 0.8: add(-0.5, "volume drying up")

    # 7. Distance from the 52-week high — momentum names ride near highs.
    window = closes[-252:] if len(closes) >= 252 else closes
    hi, lo = max(window), min(window)
    range_pct = (current - lo) / (hi - lo) if hi > lo else 0.5
    if range_pct > 0.85:   add(1.0, "near 52w high")
    elif range_pct > 0.6:  add(0.5, "upper half of range")
    elif range_pct < 0.25: add(-0.5, "near 52w low")

    return round(score, 2), factors


# ─── RISK / TRADE MATH ────────────────────────────────────────────────────────

def plan_trade(current, closes, profile):
    """
    Build the entry/stop/target plan for a paper market buy at `current`.
    ATR-based initial stop, clamped to the profile floor and 20% ceiling;
    profit target expressed as target_r multiples of initial risk.
    """
    atr = compute_atr(closes)
    stop_pct = max(float(profile["initial_stop_pct"]), min(0.20, (2 * atr) / current))
    stop = current * (1 - stop_pct)
    risk_per_share = current - stop
    target = current + float(profile["target_r"]) * risk_per_share
    return {
        "entry": round(current, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "stop_pct": round(stop_pct * 100, 1),
        "risk_per_share": round(risk_per_share, 2),
    }


def manage_position(pos, price, profile):
    """
    Ratchet the trailing stop and decide whether to exit.
    Returns (exit_reason or None, new_stop, new_peak, armed).
    Stop only ever moves up (ratchets); it arms to breakeven at activate_pct,
    then trails trail_pct under the running peak.
    """
    entry = pos["entry_price"]
    stop = pos["stop"]
    peak = max(pos["peak"] or entry, price)
    armed = bool(pos["armed"])
    activate_pct = float(profile["activate_pct"])
    trail_pct = float(profile["trail_pct"])

    if not armed and price >= entry * (1 + activate_pct):
        armed = True
    if armed:
        stop = max(stop, entry)                 # never give back to a loss
        stop = max(stop, peak * (1 - trail_pct))  # trail under the peak

    reason = None
    if price <= stop:
        reason = "trailing stop" if armed else "stop loss"
    elif price >= pos["target"]:
        reason = "profit target"

    return reason, round(stop, 2), round(peak, 2), armed


# ─── PRICE DATA ───────────────────────────────────────────────────────────────

def fetch_history(tickers):
    """Batch-download 1y of daily bars. Returns {ticker: (closes, volumes, name)}."""
    out = {}
    BATCH = 50
    uniq = list(dict.fromkeys(tickers))
    for i in range(0, len(uniq), BATCH):
        batch = uniq[i:i + BATCH]
        print(f"  Batch {i // BATCH + 1}/{(len(uniq) + BATCH - 1) // BATCH}: {batch[0]}..{batch[-1]}")
        try:
            data = yf.download(
                " ".join(batch), period="1y", group_by="ticker",
                auto_adjust=True, progress=False, threads=True,
            )
        except Exception as e:
            print(f"  Download error: {e}")
            continue
        for t in batch:
            try:
                hist = (data[t] if len(batch) > 1 and t in data.columns.get_level_values(0)
                        else (data if len(batch) == 1 else None))
                if hist is None or hist.empty:
                    continue
                closes = [float(x) for x in hist["Close"].dropna()]
                volumes = [float(x) for x in hist["Volume"].dropna()]
                if len(closes) >= 30:
                    out[t] = (closes, volumes)
            except Exception as e:
                print(f"  Parse error {t}: {e}")
    return out


NAME_CACHE = {}


def display_name(ticker):
    if ticker in NAME_CACHE:
        return NAME_CACHE[ticker]
    name = ticker
    try:
        info = yf.Ticker(ticker).info
        name = info.get("shortName") or info.get("longName") or ticker
        time.sleep(0.1)
    except Exception:
        pass
    NAME_CACHE[ticker] = name
    return name


# ─── CORE RUN ─────────────────────────────────────────────────────────────────

def run():
    cfg = load_config()
    profile = cfg["profile"]
    DOCS.mkdir(exist_ok=True)
    DB_PATH.parent.mkdir(exist_ok=True)

    con = db_connect()
    db_init(con, cfg)

    now_et = datetime.now(ET)
    today = now_et.date().isoformat()
    runlog = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "risk_profile": profile["name"],
        "actions": [],
        "errors": [],
    }

    universe = build_universe(cfg)
    open_syms = [r["symbol"] for r in con.execute("SELECT symbol FROM positions").fetchall()]
    benchmark = cfg.get("benchmark", "SPY")

    print(f"Momentum Trader [{profile['name']}] — fetching {len(universe)} tickers + "
          f"{len(open_syms)} open + benchmark...")
    prices = fetch_history(universe + open_syms + [benchmark])

    # ── 1. Manage open positions (mark-to-market, trail stops, exits) ──
    closed_this_run = []
    for pos in con.execute("SELECT * FROM positions").fetchall():
        data = prices.get(pos["symbol"])
        if not data:
            print(f"  ! no price for open position {pos['symbol']}, carrying forward")
            continue
        price = data[0][-1]
        reason, new_stop, new_peak, armed = manage_position(pos, price, profile)
        if reason:
            exit_price = price
            pnl = (exit_price - pos["entry_price"]) * pos["shares"]
            pnl_pct = (exit_price / pos["entry_price"] - 1) * 100
            risk = pos["entry_price"] - pos["initial_stop"]
            r_mult = (exit_price - pos["entry_price"]) / risk if risk > 0 else 0
            con.execute(
                """INSERT INTO trades (symbol, name, entry_date, entry_price, exit_date,
                   exit_price, shares, pnl, pnl_pct, r_multiple, exit_reason, risk_profile)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pos["symbol"], pos["name"], pos["entry_date"], pos["entry_price"], today,
                 round(exit_price, 2), pos["shares"], round(pnl, 2), round(pnl_pct, 2),
                 round(r_mult, 2), reason, pos["risk_profile"]),
            )
            set_cash(con, get_account(con)["cash"] + exit_price * pos["shares"])
            con.execute("DELETE FROM positions WHERE id = ?", (pos["id"],))
            closed_this_run.append((pos["symbol"], reason, round(pnl, 2), round(r_mult, 2)))
            con.execute("INSERT INTO picks (run_at, symbol, action, note) VALUES (?,?,?,?)",
                        (runlog["run_at"], pos["symbol"], "SELL",
                         f"{reason} @ ${exit_price:.2f} ({pnl_pct:+.1f}%, {r_mult:+.2f}R)"))
            runlog["actions"].append(f"SELL {pos['symbol']} — {reason} {pnl_pct:+.1f}%")
        else:
            con.execute(
                "UPDATE positions SET stop=?, peak=?, armed=?, last_price=? WHERE id=?",
                (new_stop, new_peak, int(armed), round(price, 2), pos["id"]),
            )
    con.commit()

    # ── 2. Rank the universe by momentum ──
    ranked = []
    for t in universe:
        data = prices.get(t)
        if not data:
            continue
        closes, volumes = data
        score, factors = momentum_score(closes, volumes)
        if score is None:
            continue
        ranked.append({
            "ticker": t, "score": score, "price": round(closes[-1], 2),
            "factors": factors, "r1": _ret(closes, 21), "r3": _ret(closes, 63),
            "closes": closes,
        })
    ranked.sort(key=lambda x: (-x["score"], x["ticker"]))
    print(f"Ranked {len(ranked)} names. Top: "
          + ", ".join(f"{r['ticker']}({r['score']})" for r in ranked[:5]))

    # ── 3. Enter the top qualifying candidate (once per calendar day) ──
    account = get_account(con)
    held = {r["symbol"] for r in con.execute("SELECT symbol FROM positions").fetchall()}
    n_open = len(held)
    # Count entries made today whether still open or already closed same day, so
    # a same-day stop-out never unlocks a second entry.
    entered_today = (
        con.execute("SELECT COUNT(*) c FROM positions WHERE entry_date = ?", (today,)).fetchone()["c"]
        + con.execute("SELECT COUNT(*) c FROM trades WHERE entry_date = ?", (today,)).fetchone()["c"]
    )
    # T+1 settlement guard: proceeds from a same-day sale are unsettled, so never
    # enter on the same calendar day as any sale.
    sold_today = con.execute(
        "SELECT COUNT(*) c FROM trades WHERE exit_date = ?", (today,)
    ).fetchone()["c"]

    entry_action = None
    if entered_today:
        entry_action = ("skip", "already entered a position today (one entry / day)")
    elif sold_today:
        entry_action = ("skip", "sold today — waiting for T+1 settlement before re-entering")
    elif n_open >= profile["max_positions"]:
        entry_action = ("skip", f"at max positions ({profile['max_positions']})")
    else:
        pick = next((r for r in ranked
                     if r["ticker"] not in held and r["score"] >= profile["min_momentum"]),
                    None)
        if pick is None:
            entry_action = ("skip", f"no candidate scored ≥ {profile['min_momentum']}")
        else:
            budget = account["cash"] * float(profile["deploy_fraction"])
            plan = plan_trade(pick["price"], pick["closes"], profile)
            shares = int(budget // plan["entry"])
            if shares < 1:
                entry_action = ("skip", f"insufficient cash for 1 share of {pick['ticker']}")
            else:
                name = display_name(pick["ticker"])
                con.execute(
                    """INSERT INTO positions (symbol, name, entry_date, entry_price, shares,
                       initial_stop, stop, peak, target, armed, score, risk_profile, last_price)
                       VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?)""",
                    (pick["ticker"], name, today, plan["entry"], shares, plan["stop"],
                     plan["stop"], plan["entry"], plan["target"], pick["score"],
                     profile["name"], plan["entry"]),
                )
                set_cash(con, account["cash"] - plan["entry"] * shares)
                con.execute("INSERT INTO picks (run_at, symbol, action, note) VALUES (?,?,?,?)",
                            (runlog["run_at"], pick["ticker"], "BUY",
                             f"{shares} sh @ ${plan['entry']:.2f}, stop ${plan['stop']:.2f}, "
                             f"target ${plan['target']:.2f} (score {pick['score']})"))
                entry_action = ("buy", {
                    "ticker": pick["ticker"], "name": name, "shares": shares,
                    "plan": plan, "score": pick["score"], "factors": pick["factors"],
                })
                runlog["actions"].append(
                    f"BUY {pick['ticker']} {shares}sh @ ${plan['entry']:.2f} (score {pick['score']})")
    con.commit()

    # ── 4. Snapshot equity ──
    positions_value = 0.0
    for pos in con.execute("SELECT * FROM positions").fetchall():
        data = prices.get(pos["symbol"])
        px = data[0][-1] if data else pos["last_price"] or pos["entry_price"]
        positions_value += px * pos["shares"]
    account = get_account(con)
    total_equity = account["cash"] + positions_value
    bench_price = prices[benchmark][0][-1] if benchmark in prices else None
    con.execute(
        """INSERT INTO equity (snap_date, cash, positions_value, total_equity, benchmark_price)
           VALUES (?,?,?,?,?)
           ON CONFLICT(snap_date) DO UPDATE SET
             cash=excluded.cash, positions_value=excluded.positions_value,
             total_equity=excluded.total_equity, benchmark_price=excluded.benchmark_price""",
        (today, round(account["cash"], 2), round(positions_value, 2),
         round(total_equity, 2), round(bench_price, 2) if bench_price else None),
    )
    con.commit()

    # ── 5. Write outputs ──
    updated = now_et.strftime("%B %d, %Y at %H:%M ET")
    ctx = build_context(con, cfg, ranked, entry_action, closed_this_run, updated, prices)
    (DOCS / "momentum_trader.html").write_text(render_dashboard(ctx), encoding="utf-8")
    email_html, subject = render_email(ctx)
    (DOCS / "momentum_email.html").write_text(email_html, encoding="utf-8")
    (DOCS / "momentum_email_subject.txt").write_text(subject, encoding="utf-8")

    runlog["equity"] = round(total_equity, 2)
    runlog["cash"] = round(account["cash"], 2)
    runlog["open_positions"] = len(held) + (1 if entry_action and entry_action[0] == "buy" else 0)
    runlog["closed_this_run"] = len(closed_this_run)
    RUNLOG_PATH.write_text(json.dumps(runlog, indent=2), encoding="utf-8")

    con.close()
    print(f"Done. Equity ${total_equity:,.2f} | Cash ${account['cash']:,.2f}")
    print(f"Subject: {subject}")


# ─── REPORTING CONTEXT ────────────────────────────────────────────────────────

def build_context(con, cfg, ranked, entry_action, closed_this_run, updated, prices):
    account = get_account(con)
    starting = account["starting_cash"]

    open_positions = []
    positions_value = 0.0
    for pos in con.execute("SELECT * FROM positions ORDER BY entry_date").fetchall():
        data = prices.get(pos["symbol"])
        px = data[0][-1] if data else (pos["last_price"] or pos["entry_price"])
        mv = px * pos["shares"]
        positions_value += mv
        unreal = (px - pos["entry_price"]) * pos["shares"]
        unreal_pct = (px / pos["entry_price"] - 1) * 100
        risk = pos["entry_price"] - pos["initial_stop"]
        r_now = (px - pos["entry_price"]) / risk if risk > 0 else 0
        open_positions.append({
            "symbol": pos["symbol"], "name": pos["name"], "entry_date": pos["entry_date"],
            "entry": pos["entry_price"], "price": round(px, 2), "shares": pos["shares"],
            "stop": pos["stop"], "target": pos["target"], "mv": round(mv, 2),
            "unreal": round(unreal, 2), "unreal_pct": round(unreal_pct, 1),
            "r_now": round(r_now, 2), "armed": bool(pos["armed"]), "score": pos["score"],
        })

    total_equity = account["cash"] + positions_value
    total_return = (total_equity / starting - 1) * 100 if starting else 0

    closed = con.execute("SELECT * FROM trades ORDER BY exit_date DESC, id DESC").fetchall()
    closed = [dict(r) for r in closed]
    wins = [t for t in closed if t["pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100 if closed else 0
    avg_r = sum(t["r_multiple"] for t in closed) / len(closed) if closed else 0
    realized = sum(t["pnl"] for t in closed)

    equity_rows = con.execute(
        "SELECT snap_date, total_equity, benchmark_price FROM equity ORDER BY snap_date"
    ).fetchall()
    curve = [dict(r) for r in equity_rows]

    # Benchmark buy-and-hold from inception.
    bench_return = None
    bench_prices = [r["benchmark_price"] for r in curve if r["benchmark_price"]]
    if len(bench_prices) >= 2 and bench_prices[0]:
        bench_return = (bench_prices[-1] / bench_prices[0] - 1) * 100

    return {
        "cfg": cfg, "profile": cfg["profile"], "updated": updated,
        "starting": starting, "cash": account["cash"], "positions_value": positions_value,
        "total_equity": total_equity, "total_return": total_return,
        "open_positions": open_positions, "closed": closed,
        "win_rate": win_rate, "avg_r": avg_r, "realized": realized,
        "n_trades": len(closed), "curve": curve, "bench_return": bench_return,
        "benchmark": cfg.get("benchmark", "SPY"),
        "ranked": ranked[:20], "entry_action": entry_action,
        "closed_this_run": closed_this_run,
    }


# ─── DASHBOARD (GitHub Pages) ─────────────────────────────────────────────────

def _sparkline(curve, width=680, height=120):
    vals = [r["total_equity"] for r in curve]
    if len(vals) < 2:
        return '<div class="empty">Equity curve appears after the second run.</div>'
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pts = []
    for i, v in enumerate(vals):
        x = i / (len(vals) - 1) * width
        y = height - (v - lo) / span * (height - 10) - 5
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    up = vals[-1] >= vals[0]
    color = "#22c55e" if up else "#ef4444"
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'style="width:100%;height:{height}px">'
        f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{poly}"/>'
        f'</svg>'
    )


def render_dashboard(c):
    p = c["profile"]
    ret_color = "#22c55e" if c["total_return"] >= 0 else "#ef4444"

    # Action banner
    ea = c["entry_action"]
    if ea and ea[0] == "buy":
        d = ea[1]
        banner = (
            f'<div class="banner buy"><span class="tag">NEW ENTRY</span> '
            f'<b>{d["ticker"]}</b> — {d["name"]} · {d["shares"]} sh @ '
            f'${d["plan"]["entry"]:.2f} · stop ${d["plan"]["stop"]:.2f} · '
            f'target ${d["plan"]["target"]:.2f} · momentum {d["score"]}'
            f'<div class="why">{" · ".join(d["factors"][:6])}</div></div>'
        )
    else:
        note = ea[1] if ea else "no action"
        banner = f'<div class="banner flat"><span class="tag">NO ENTRY</span> {note}</div>'

    def pos_rows():
        if not c["open_positions"]:
            return '<tr><td colspan="9" class="empty">No open positions.</td></tr>'
        out = []
        for x in c["open_positions"]:
            col = "#22c55e" if x["unreal"] >= 0 else "#ef4444"
            status = "🔒 trailing" if x["armed"] else "○ initial stop"
            out.append(
                f'<tr><td><b>{x["symbol"]}</b><div class="sub">{x["name"][:26]}</div></td>'
                f'<td>{x["entry_date"]}</td><td>${x["entry"]:.2f}</td>'
                f'<td>${x["price"]:.2f}</td><td>${x["stop"]:.2f}</td>'
                f'<td>${x["target"]:.2f}</td><td>{x["shares"]}</td>'
                f'<td style="color:{col}">${x["unreal"]:,.0f} ({x["unreal_pct"]:+.1f}%)'
                f'<div class="sub">{x["r_now"]:+.2f}R</div></td>'
                f'<td class="sub">{status}</td></tr>'
            )
        return "".join(out)

    def trade_rows():
        if not c["closed"]:
            return '<tr><td colspan="8" class="empty">No closed trades yet.</td></tr>'
        out = []
        for t in c["closed"][:40]:
            col = "#22c55e" if t["pnl"] >= 0 else "#ef4444"
            out.append(
                f'<tr><td><b>{t["symbol"]}</b></td><td>{t["entry_date"]}</td>'
                f'<td>{t["exit_date"]}</td><td>${t["entry_price"]:.2f}</td>'
                f'<td>${t["exit_price"]:.2f}</td>'
                f'<td style="color:{col}">${t["pnl"]:,.0f} ({t["pnl_pct"]:+.1f}%)</td>'
                f'<td style="color:{col}">{t["r_multiple"]:+.2f}R</td>'
                f'<td class="sub">{t["exit_reason"]}</td></tr>'
            )
        return "".join(out)

    def rank_rows():
        out = []
        for i, r in enumerate(c["ranked"], 1):
            out.append(
                f'<tr><td>{i}</td><td><b>{r["ticker"]}</b></td>'
                f'<td>${r["price"]:.2f}</td><td><b>{r["score"]}</b></td>'
                f'<td class="sub">{" · ".join(r["factors"][:5])}</td></tr>'
            )
        return "".join(out)

    bench = ""
    if c["bench_return"] is not None:
        bcol = "#22c55e" if c["total_return"] >= c["bench_return"] else "#ef4444"
        bench = (f'<div class="stat"><div class="lbl">vs {c["benchmark"]} (buy&hold)</div>'
                 f'<div class="val" style="color:{bcol}">{c["total_return"] - c["bench_return"]:+.1f} pts</div>'
                 f'<div class="sub">{c["benchmark"]} {c["bench_return"]:+.1f}%</div></div>')

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Momentum Trader — Paper Portfolio</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#0b0f17; color:#e5e7eb; font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }}
  .wrap {{ max-width:1040px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:24px; margin:0 0 4px; }}
  .meta {{ color:#94a3b8; font-size:13px; margin-bottom:20px; }}
  .pill {{ display:inline-block; background:#1e293b; color:#93c5fd; border-radius:999px;
           padding:2px 10px; font-size:12px; margin-left:6px; text-transform:uppercase; letter-spacing:.04em; }}
  .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:20px; }}
  .stat {{ background:#111827; border:1px solid #1f2937; border-radius:12px; padding:14px 16px; }}
  .stat .lbl {{ color:#94a3b8; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  .stat .val {{ font-size:22px; font-weight:700; margin-top:4px; }}
  .stat .sub {{ color:#64748b; font-size:12px; }}
  .banner {{ border-radius:12px; padding:14px 16px; margin-bottom:22px; font-size:15px; }}
  .banner.buy {{ background:#052e1a; border:1px solid #166534; }}
  .banner.flat {{ background:#1f2937; border:1px solid #374151; color:#cbd5e1; }}
  .banner .tag {{ font-size:11px; font-weight:700; letter-spacing:.06em; background:#166534;
                  color:#dcfce7; border-radius:6px; padding:2px 8px; margin-right:8px; }}
  .banner.flat .tag {{ background:#475569; color:#e2e8f0; }}
  .banner .why {{ color:#86efac; font-size:12px; margin-top:6px; }}
  .banner.flat .why {{ color:#94a3b8; }}
  h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.05em; color:#94a3b8; margin:26px 0 10px; }}
  .card {{ background:#111827; border:1px solid #1f2937; border-radius:12px; padding:6px 4px; overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
  th {{ text-align:left; color:#64748b; font-weight:600; font-size:11px; text-transform:uppercase;
        letter-spacing:.04em; padding:8px 10px; border-bottom:1px solid #1f2937; }}
  td {{ padding:9px 10px; border-bottom:1px solid #161e2e; vertical-align:top; }}
  tr:last-child td {{ border-bottom:none; }}
  .sub {{ color:#64748b; font-size:11.5px; }}
  .empty {{ color:#64748b; text-align:center; padding:20px; }}
  .disc {{ color:#64748b; font-size:12px; margin-top:34px; border-top:1px solid #1f2937; padding-top:16px; }}
</style></head><body><div class="wrap">
  <h1>Momentum Trader <span class="pill">{p['name']}</span> <span class="pill">paper</span></h1>
  <div class="meta">Simulated portfolio · one momentum pick per day · updated {c['updated']}</div>

  <div class="stats">
    <div class="stat"><div class="lbl">Total Equity</div><div class="val">${c['total_equity']:,.0f}</div>
      <div class="sub">from ${c['starting']:,.0f} start</div></div>
    <div class="stat"><div class="lbl">Total Return</div>
      <div class="val" style="color:{ret_color}">{c['total_return']:+.1f}%</div>
      <div class="sub">${c['total_equity'] - c['starting']:,.0f}</div></div>
    {bench}
    <div class="stat"><div class="lbl">Cash</div><div class="val">${c['cash']:,.0f}</div>
      <div class="sub">{len(c['open_positions'])} open positions</div></div>
    <div class="stat"><div class="lbl">Win Rate</div><div class="val">{c['win_rate']:.0f}%</div>
      <div class="sub">{c['n_trades']} closed · avg {c['avg_r']:+.2f}R</div></div>
  </div>

  {banner}

  <h2>Equity Curve</h2>
  <div class="card" style="padding:14px 16px">{_sparkline(c['curve'])}</div>

  <h2>Open Positions</h2>
  <div class="card"><table>
    <tr><th>Symbol</th><th>Entry Date</th><th>Entry</th><th>Last</th><th>Stop</th>
        <th>Target</th><th>Shares</th><th>Unrealized</th><th>Status</th></tr>
    {pos_rows()}
  </table></div>

  <h2>Closed Trades</h2>
  <div class="card"><table>
    <tr><th>Symbol</th><th>In</th><th>Out</th><th>Entry</th><th>Exit</th>
        <th>P&amp;L</th><th>R</th><th>Reason</th></tr>
    {trade_rows()}
  </table></div>

  <h2>Top Momentum Candidates</h2>
  <div class="card"><table>
    <tr><th>#</th><th>Symbol</th><th>Price</th><th>Score</th><th>Why</th></tr>
    {rank_rows()}
  </table></div>

  <div class="disc"><b>Not financial advice.</b> This is a paper (simulated) portfolio.
  Fills, stops and targets are book-kept at daily closing prices and ignore slippage,
  spreads, and fees. Deterministic momentum ranking — no discretion, no guarantee of
  future results. Built for education, inspired by the AI Momentum Trader project.</div>
</div></body></html>"""


# ─── EMAIL ────────────────────────────────────────────────────────────────────

def render_email(c):
    ea = c["entry_action"]
    ret_color = "#16a34a" if c["total_return"] >= 0 else "#dc2626"

    if ea and ea[0] == "buy":
        d = ea[1]
        headline = f"BUY {d['ticker']}"
        action_html = (
            f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;'
            f'padding:14px 16px;margin:0 0 18px"><b style="color:#166534">NEW ENTRY · '
            f'{d["ticker"]}</b> — {d["name"]}<br>{d["shares"]} sh @ ${d["plan"]["entry"]:.2f} · '
            f'stop ${d["plan"]["stop"]:.2f} · target ${d["plan"]["target"]:.2f} · '
            f'momentum {d["score"]}<br><span style="color:#15803d;font-size:12px">'
            f'{" · ".join(d["factors"][:6])}</span></div>'
        )
    else:
        headline = "No entry"
        note = ea[1] if ea else "no action"
        action_html = (
            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
            f'padding:14px 16px;margin:0 0 18px;color:#475569"><b>No entry today</b> — {note}</div>'
        )

    closed_html = ""
    if c["closed_this_run"]:
        rows = "".join(
            f'<li>{sym} — {reason}: '
            f'<b style="color:{"#16a34a" if pnl>=0 else "#dc2626"}">${pnl:,.0f} ({r:+.2f}R)</b></li>'
            for sym, reason, pnl, r in c["closed_this_run"]
        )
        closed_html = (f'<p style="margin:0 0 6px;font-weight:600">Closed this run</p>'
                       f'<ul style="margin:0 0 18px;padding-left:18px">{rows}</ul>')

    pos_rows = ""
    for x in c["open_positions"]:
        col = "#16a34a" if x["unreal"] >= 0 else "#dc2626"
        pos_rows += (
            f'<tr><td style="padding:6px 8px"><b>{x["symbol"]}</b></td>'
            f'<td style="padding:6px 8px">${x["price"]:.2f}</td>'
            f'<td style="padding:6px 8px">${x["stop"]:.2f}</td>'
            f'<td style="padding:6px 8px;color:{col}">{x["unreal_pct"]:+.1f}% ({x["r_now"]:+.2f}R)</td></tr>'
        )
    if not pos_rows:
        pos_rows = '<tr><td colspan="4" style="padding:6px 8px;color:#94a3b8">No open positions.</td></tr>'

    bench_line = ""
    if c["bench_return"] is not None:
        bench_line = (f' · vs {c["benchmark"]} {c["bench_return"]:+.1f}% '
                      f'({c["total_return"] - c["bench_return"]:+.1f} pts)')

    subject = (f"📈 Momentum Trader [{c['profile']['name']}] — {headline} | "
               f"Equity ${c['total_equity']:,.0f} ({c['total_return']:+.1f}%)")

    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:620px;
      margin:0 auto;color:#0f172a">
      <h2 style="margin:0 0 2px">Momentum Trader
        <span style="font-size:12px;background:#e2e8f0;border-radius:6px;padding:2px 8px;
          text-transform:uppercase;letter-spacing:.04em">{c['profile']['name']} · paper</span></h2>
      <p style="color:#64748b;margin:0 0 16px;font-size:13px">Updated {c['updated']}</p>

      <div style="font-size:26px;font-weight:800;color:{ret_color}">
        ${c['total_equity']:,.0f} <span style="font-size:15px">({c['total_return']:+.1f}%)</span></div>
      <p style="color:#64748b;margin:2px 0 18px;font-size:13px">
        Cash ${c['cash']:,.0f} · {len(c['open_positions'])} open · win rate {c['win_rate']:.0f}%
        · avg {c['avg_r']:+.2f}R{bench_line}</p>

      {action_html}
      {closed_html}

      <p style="margin:0 0 6px;font-weight:600">Open positions</p>
      <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:18px">
        <tr style="color:#64748b;text-align:left">
          <th style="padding:6px 8px">Symbol</th><th style="padding:6px 8px">Last</th>
          <th style="padding:6px 8px">Stop</th><th style="padding:6px 8px">Unrealized</th></tr>
        {pos_rows}
      </table>

      <p style="color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0;padding-top:12px">
        Paper (simulated) portfolio — not financial advice. Deterministic momentum ranking;
        fills booked at daily closes, ignoring slippage and fees.
        <a href="https://gtmautomationops-dev.github.io/market-scanner/momentum_trader.html">
        Full dashboard →</a></p>
    </div>"""
    return html, subject


if __name__ == "__main__":
    run()
