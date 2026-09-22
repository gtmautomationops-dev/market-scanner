#!/usr/bin/env python3
"""
Houston — mission control. The coordinator that sits above the other desks.

Every other agent in this repo runs its own narrow beat: Alex hunts ideas, Sarah
watches risk, Elena writes the weekly report, Marcus reads options flow, the
Momentum trader runs a paper book, and the Congress / Insider trackers scrape
filings. Houston is the layer above them — the one the story calls "mission
control", where every bot reports in and one unified read comes out.

Houston does NOT trade and keeps no book of its own. Once a day it:

  1. Marks both books (My Picks + Momentum) to market with live prices.
  2. Ranks the ETF universe with the same transparent momentum engine the rest of
     the fund uses, and plans out the top fresh ETF ideas — the ETF lens leads.
  3. Applies Sarah's exact risk rules across every open position and rolls them
     into one fund-wide checklist.
  4. Reads each desk's latest FILED report (the runlogs committed to main) and
     puts them on a single roll-call, each stamped with how old it is — so a
     stale report is never mistaken for a live one.

Then it publishes one dashboard + one daily-brief email that ties it all
together. Advisory only. Houston synthesizes; it never places an order.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fund_common as fc
from momentum_trader import (
    momentum_score, plan_trade, fetch_history, display_name, LEVERAGED,
)
from scanner import US_ETFS, CA_ETFS, ETF_SET, BOND_ETF_SET

CONFIG_PATH = fc.CONFIG / "houston.yml"
SLUG = "houston"

# The desks that file a report to main. Alex and Marcus are stateless (they
# recompute on their own pages and commit nothing), so they can't be ingested
# here — Houston does the ETF slice of Alex's job itself, and links to both.
DESKS = [
    ("risk_sarah",      "Sarah · Risk",        "risk_sarah.html"),
    ("momentum_trader", "Momentum · Paper Book", "momentum_trader.html"),
    ("report_elena",    "Elena · Weekly Report", "report_elena.html"),
    ("congress",        "Congress Tracker",     "congress_tracker.html"),
    ("insider_radar",   "Insider Radar",        "insider_radar.html"),
]


# ─── ETF LENS (pure — takes prices, so it's unit-testable offline) ─────────────

def etf_universe(cfg):
    """The ETF ticker list Houston ranks, honoring the config toggles."""
    tickers = list(US_ETFS)
    if cfg.get("include_canada", True):
        tickers += CA_ETFS
    if cfg.get("exclude_leveraged", True):
        tickers = [t for t in tickers if t not in LEVERAGED]
    if not cfg.get("include_bond_etfs", True):
        tickers = [t for t in tickers if t not in BOND_ETF_SET]
    seen, out = set(), []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def is_etf(ticker):
    """True if the symbol is one of the fund's known ETFs."""
    return ticker in ETF_SET


def rank_etfs(prices, universe, bench_closes):
    """Score every ETF in the universe. Returns a list sorted best-first."""
    ranked = []
    for t in universe:
        data = prices.get(t)
        if not data:
            continue
        closes, volumes = data
        score, factors = momentum_score(closes, volumes, bench_closes)
        if score is None:
            continue
        ranked.append({"ticker": t, "score": score, "price": round(closes[-1], 2),
                       "factors": factors, "closes": closes})
    ranked.sort(key=lambda x: (-x["score"], x["ticker"]))
    return ranked


def _top_factors(factors, n=6):
    def mag(f):
        try:
            return abs(float(f.split()[0]))
        except (ValueError, IndexError):
            return 0.0
    return " · ".join(sorted(factors, key=mag, reverse=True)[:n])


def etf_ideas(ranked, held, min_score, top_n, plan_profile):
    """Top-scoring ETFs Houston doesn't already hold, each with a trade plan."""
    rank_of = {r["ticker"]: i + 1 for i, r in enumerate(ranked)}
    ideas = []
    for r in ranked:
        if r["ticker"] in held or r["score"] < min_score:
            continue
        plan = plan_trade(r["price"], r["closes"], plan_profile)
        ideas.append({
            "ticker": r["ticker"], "name": display_name(r["ticker"]),
            "score": r["score"], "price": r["price"], "rank": rank_of[r["ticker"]],
            "plan": plan, "thesis": _top_factors(r["factors"], 6),
        })
        if len(ideas) >= top_n:
            break
    return ideas


def held_etf_health(positions, ranked, min_score):
    """
    For every ETF held across both books, where does it sit on today's ETF
    leaderboard? Pure — takes the ranked list, no network.
    """
    rank_of = {r["ticker"]: i + 1 for i, r in enumerate(ranked)}
    score_of = {r["ticker"]: r["score"] for r in ranked}
    health = []
    for pos in positions:
        sym = pos["symbol"]
        if not is_etf(sym):
            continue
        r = rank_of.get(sym)
        sc = score_of.get(sym)
        if sc is None:
            verdict = "not scored"
        elif sc >= min_score:
            verdict = "leading the ETF pack" if r and r <= 5 else "still qualifies"
        else:
            verdict = "momentum fading — watch"
        health.append({"symbol": sym, "book": pos["book"], "rank": r, "score": sc,
                        "unreal_pct": pos["unreal_pct"], "verdict": verdict})
    return health


# ─── FUND-WIDE RISK (reuses Sarah's exact rules — pure) ───────────────────────

def fund_risk(all_positions, total_exposure, momentum_curve_values, cfg):
    """
    Run Sarah's per-position and fund-level rules across every open position.
    Returns (checklist, n_alert, n_watch, momentum_drawdown_pct).
    """
    reviewed = [{"pos": p, "flags": fc.position_flags(p, cfg)} for p in all_positions]

    conc = fc.concentration_flags(all_positions, total_exposure, cfg)
    conc_by_sym = {c["symbol"]: c for c in conc}
    for r in reviewed:
        c = conc_by_sym.get(r["pos"]["symbol"])
        if c:
            r["flags"].append(c)

    mom_dd = fc.drawdown_from_peak(momentum_curve_values) if momentum_curve_values else 0.0
    dd_alert = float(cfg.get("drawdown_alert_pct", 10.0))
    fund_flags = []
    if momentum_curve_values and mom_dd <= -dd_alert:
        fund_flags.append({"level": "alert", "code": "drawdown",
                           "msg": f"Momentum book {mom_dd:.1f}% off its peak "
                                  f"(alert at −{dd_alert:.0f}%)"})

    checklist = []
    for r in reviewed:
        for f in r["flags"]:
            checklist.append({**f, "symbol": r["pos"]["symbol"], "book": r["pos"]["book"],
                              "unreal_pct": r["pos"]["unreal_pct"], "price": r["pos"]["price"],
                              "is_etf": is_etf(r["pos"]["symbol"])})
    checklist += [{**f, "symbol": "FUND", "book": "—", "unreal_pct": None,
                   "price": None, "is_etf": False} for f in fund_flags]
    order = {"alert": 0, "watch": 1}
    checklist.sort(key=lambda x: (order.get(x["level"], 2), x["symbol"]))
    n_alert = sum(1 for c in checklist if c["level"] == "alert")
    n_watch = sum(1 for c in checklist if c["level"] == "watch")
    return checklist, n_alert, n_watch, mom_dd


# ─── DESK ROLL-CALL (pure — takes parsed logs + a 'now') ──────────────────────

def _f(v, dflt=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return dflt


def read_runlog(key):
    """Load data/<key>_runlog.json, or None if the desk hasn't filed one."""
    p = fc.DATA / f"{key}_runlog.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def age_hours(run_at, now):
    """Hours between an ISO timestamp and `now` (aware). None if unparseable."""
    if not run_at:
        return None
    try:
        dt = datetime.fromisoformat(str(run_at))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 3600.0


def age_label(hours):
    if hours is None:
        return "never"
    if hours < 1:
        m = max(1, int(round(hours * 60)))
        return "just now" if hours < 1 / 60 else f"{m}m ago"
    if hours < 48:
        return f"{int(round(hours))}h ago"
    return f"{int(round(hours / 24))}d ago"


def summarize_desk(key, log, now, stale_hours):
    """
    Turn one desk's runlog into a roll-call row: {level, headline, age_label,
    stale, filed}. Pure — no I/O. `log` is the parsed dict, or None if not filed.
    """
    if log is None:
        return {"level": "info", "headline": "no report filed to main yet",
                "age_label": "never", "stale": True, "filed": False, "run_at": None}

    hours = age_hours(log.get("run_at"), now)
    stale = hours is None or hours > stale_hours

    if key == "risk_sarah":
        a, w = int(_f(log.get("alerts"))), int(_f(log.get("watches")))
        rev = int(_f(log.get("positions_reviewed")))
        dd = log.get("momentum_drawdown_pct")
        level = "alert" if a else ("watch" if w else "ok")
        head = f"{a} alert{'s' if a != 1 else ''} · {w} watch · {rev} positions"
        if dd is not None:
            head += f" · Momentum {_f(dd):+.1f}% off peak"
    elif key == "momentum_trader":
        errs = log.get("errors") or []
        eq, opn = _f(log.get("equity")), int(_f(log.get("open_positions")))
        closed = int(_f(log.get("closed_this_run")))
        prof = log.get("risk_profile", "—")
        level = "alert" if errs else "info"
        head = (f"paper equity ${eq:,.0f} · {opn} open · "
                f"{closed} closed this run · {prof} profile")
        if errs:
            head += f" · {len(errs)} error(s)"
    elif key == "report_elena":
        cpnl, cret = _f(log.get("combined_pnl")), _f(log.get("combined_return_pct"))
        wk, spy = _f(log.get("week_pnl")), _f(log.get("spy_return_pct"))
        level = "info"
        head = (f"combined P&L ${cpnl:,.0f} ({cret:+.1f}%) · "
                f"week ${wk:+,.0f} · SPY {spy:+.1f}%")
    elif key == "congress":
        errs = log.get("errors") or []
        ptrs = int(_f(log.get("ptrs_in_window")))
        trades = int(_f(log.get("trades_stored")))
        level = "alert" if errs else "info"
        head = f"{ptrs} PTRs in window · {trades} new trade(s) stored"
        if errs:
            head += f" · {len(errs)} error(s)"
    elif key == "insider_radar":
        errs = log.get("errors") or []
        f4 = int(_f(log.get("form4_in_window")))
        stored = int(_f(log.get("stored")))
        offerings = int(_f(log.get("offering_purchases_flagged")))
        level = "alert" if errs else "info"
        head = f"{f4} Form 4s in window · {stored} stored · {offerings} offerings flagged"
        if errs:
            head += f" · {len(errs)} error(s)"
    else:
        level, head = "info", "reported"

    return {"level": level, "headline": head, "age_label": age_label(hours),
            "stale": stale, "filed": True, "run_at": log.get("run_at")}


# ─── ORCHESTRATION ────────────────────────────────────────────────────────────

def run():
    cfg = fc.load_yaml(CONFIG_PATH, {})
    benchmark = str(cfg.get("benchmark", "SPY")).upper()
    min_score = float(cfg.get("min_score", 4.0))
    etf_top_n = int(cfg.get("etf_top_n", 10))
    etf_idea_n = int(cfg.get("etf_idea_n", 4))
    stale_hours = float(cfg.get("stale_report_hours", 48))
    plan_profile = {"initial_stop_pct": float(cfg.get("plan_stop_pct", 0.08)),
                    "target_r": float(cfg.get("plan_target_r", 2.5))}

    holdings = fc.load_holdings()
    universe = etf_universe(cfg)

    # Discover Momentum symbols (fallback-priced) so we fetch everything at once.
    stub = fc.read_momentum_book({})
    mom_syms = [p["symbol"] for p in stub["positions"]] if stub else []
    my_syms = [p["symbol"] for p in holdings["open"]]

    print(f"Houston: ranking {len(universe)} ETFs + marking "
          f"{len(my_syms)} My Picks / {len(mom_syms)} Momentum + {benchmark}...")
    prices = fetch_history(universe + my_syms + mom_syms + [benchmark])

    my_book = fc.mark_my_picks(holdings, prices)
    momentum_book = fc.read_momentum_book(prices)
    bench_closes = prices[benchmark][0] if benchmark in prices else None
    bench_px = bench_closes[-1] if bench_closes else None

    all_positions = list(my_book["positions"]) + (
        momentum_book["positions"] if momentum_book else [])
    total_exposure = my_book["market_value"] + (
        momentum_book["positions_value"] if momentum_book else 0.0)
    held = fc.held_symbols(my_book, momentum_book)

    # ── ETF lens ──
    ranked = rank_etfs(prices, universe, bench_closes)
    ideas = etf_ideas(ranked, held, min_score, etf_idea_n, plan_profile)
    etf_health = held_etf_health(all_positions, ranked, min_score)

    # ── Fund-wide risk (Sarah's rules) ──
    mom_curve = [row["total_equity"] for row in momentum_book["curve"]] if momentum_book else []
    checklist, n_alert, n_watch, mom_dd = fund_risk(
        all_positions, total_exposure, mom_curve, cfg)

    # ── Desk roll-call ──
    now = datetime.now(timezone.utc)
    roll_call = []
    for key, name, page_file in DESKS:
        summary = summarize_desk(key, read_runlog(key), now, stale_hours)
        roll_call.append({"key": key, "name": name, "page": page_file, **summary})

    combined_pnl = my_book["total_pnl"] + (momentum_book["total_pnl"] if momentum_book else 0.0)

    # ── Email gating ("when needed") ──
    level = str(cfg.get("notify_level", "watch")).lower()
    if level == "always":
        should_send = True
    elif level == "alert":
        should_send = n_alert > 0
    else:  # "watch" (default for the daily brief)
        should_send = (n_alert + n_watch) > 0
    fc.write_send_flag(SLUG, should_send)

    updated = fc.now_et_str()
    dashboard = render_dashboard(ideas, ranked[:etf_top_n], etf_health, checklist,
                                 roll_call, my_book, momentum_book, combined_pnl,
                                 n_alert, n_watch, mom_dd, min_score, updated)
    email_html, subject = render_email(ideas, checklist, roll_call, combined_pnl,
                                       n_alert, n_watch, updated)
    fc.write_agent_outputs(SLUG, dashboard, email_html, subject)
    fc.write_runlog(SLUG, {
        "etfs_ranked": len(ranked),
        "etf_ideas": [i["ticker"] for i in ideas],
        "positions_reviewed": len(all_positions),
        "alerts": n_alert, "watches": n_watch,
        "momentum_drawdown_pct": mom_dd,
        "combined_pnl": round(combined_pnl, 2),
        "desks": {r["key"]: {"level": r["level"], "stale": r["stale"],
                             "filed": r["filed"], "age": r["age_label"]}
                  for r in roll_call},
        "notify_level": level, "emailed": should_send,
    })
    print(f"Houston done. {len(ideas)} ETF ideas · {n_alert} alerts / {n_watch} watches · "
          f"{sum(1 for r in roll_call if r['stale'] and r['filed'])} stale desk report(s). "
          f"Email: {'yes' if should_send else 'no (nothing needed)'}. Subject: {subject}")


# ─── RENDERING ────────────────────────────────────────────────────────────────

def _posture(n_alert, n_watch, roll_call, top_etf):
    stale = [r for r in roll_call if r["filed"] and r["stale"]]
    lead = f" · strongest ETF <b>{top_etf}</b>" if top_etf else ""
    if n_alert:
        return ("alert", "alert",
                f"{n_alert} fund-wide alert{'s' if n_alert != 1 else ''} need attention{lead}.")
    if stale:
        return ("flat", "book",
                f"No alerts, but {len(stale)} desk report{'s' if len(stale) != 1 else ''} "
                f"went stale — check the roll-call{lead}.")
    if n_watch:
        return ("flat", "watch",
                f"Nothing urgent — {n_watch} item{'s' if n_watch != 1 else ''} on watch{lead}.")
    return ("calm", "ok", f"All desks reporting, nothing tripped{lead}.")


def render_dashboard(ideas, leaderboard, etf_health, checklist, roll_call,
                     my_book, momentum_book, combined_pnl, n_alert, n_watch,
                     mom_dd, min_score, updated):
    top_etf = leaderboard[0]["ticker"] if leaderboard else None
    tone, tag, msg = _posture(n_alert, n_watch, roll_call, top_etf)
    banner = f'<div class="banner {tone}"><span class="tag {tag}">MISSION CONTROL</span>{msg}</div>'

    n_positions = len(my_book["positions"]) + (momentum_book["n_open"] if momentum_book else 0)
    n_etf_held = len(etf_health)
    desks_live = sum(1 for r in roll_call if r["filed"] and not r["stale"])
    stats = f"""
  <div class="stats">
    <div class="stat"><div class="lbl">Combined P&amp;L</div>
      <div class="val {fc.color_of(combined_pnl)}">{fc.money(combined_pnl)}</div>
      <div class="sub">both books · unrealized + realized</div></div>
    <div class="stat"><div class="lbl">Fund Alerts</div>
      <div class="val {'neg' if n_alert else 'pos'}">{n_alert}</div>
      <div class="sub">{n_watch} on watch · {n_positions} positions</div></div>
    <div class="stat"><div class="lbl">ETFs Held</div><div class="val">{n_etf_held}</div>
      <div class="sub">strongest today: {top_etf or '—'}</div></div>
    <div class="stat"><div class="lbl">Desks Reporting</div>
      <div class="val">{desks_live}/{len(roll_call)}</div>
      <div class="sub">fresh within window</div></div>
  </div>"""

    # ── ETF ideas ──
    if ideas:
        top = ideas[0]
        idea_banner = (f'<div class="banner calm"><span class="tag ok">TOP ETF IDEA</span>'
                       f'<b>{top["ticker"]}</b> — {top["name"]} · momentum {top["score"]} '
                       f'(#{top["rank"]} of ETF universe)<br>'
                       f'<span class="sub">entry ${top["plan"]["entry"]:.2f} · '
                       f'stop ${top["plan"]["stop"]:.2f} · target ${top["plan"]["target"]:.2f} · '
                       f'{top["thesis"]}</span></div>')
    else:
        idea_banner = (f'<div class="banner flat"><span class="tag book">QUIET</span>'
                       f'No unheld ETF scored ≥ {min_score} today.</div>')

    def idea_rows():
        if not ideas:
            return '<tr><td colspan="6" class="empty">No fresh ETF ideas above threshold.</td></tr>'
        return "".join(
            f'<tr><td><b>{x["ticker"]}</b><div class="sub">{x["name"][:30]}</div></td>'
            f'<td>#{x["rank"]}</td><td><b>{x["score"]}</b></td>'
            f'<td>${x["plan"]["entry"]:.2f}</td>'
            f'<td>${x["plan"]["stop"]:.2f} / ${x["plan"]["target"]:.2f}</td>'
            f'<td class="sub">{x["thesis"]}</td></tr>' for x in ideas)

    def board_rows():
        if not leaderboard:
            return '<tr><td colspan="5" class="empty">No ETF prices available.</td></tr>'
        return "".join(
            f'<tr><td>{i}</td><td><b>{r["ticker"]}</b></td>'
            f'<td>${r["price"]:.2f}</td><td><b>{r["score"]}</b></td>'
            f'<td class="sub">{_top_factors(r["factors"], 5)}</td></tr>'
            for i, r in enumerate(leaderboard, 1))

    def health_rows():
        if not etf_health:
            return ('<tr><td colspan="5" class="empty">No ETFs held in either book. '
                    'Add yours in config/my_picks.yml.</td></tr>')
        out = []
        for h in etf_health:
            rank = f'#{h["rank"]}' if h["rank"] else "—"
            sc = f'{h["score"]}' if h["score"] is not None else "—"
            warn = "watch" if "fading" in h["verdict"] else "sub"
            out.append(
                f'<tr><td><b>{h["symbol"]}</b></td>'
                f'<td><span class="tag book">{h["book"]}</span></td>'
                f'<td>{rank} · score {sc}</td>'
                f'<td class="{fc.color_of(h["unreal_pct"])}">{h["unreal_pct"]:+.1f}%</td>'
                f'<td class="{warn}">{h["verdict"]}</td></tr>')
        return "".join(out)

    # ── Fund risk ──
    def checklist_rows():
        if not checklist:
            return ('<tr><td colspan="4" class="empty">Nothing flagged. Every position '
                    'is inside its risk limits.</td></tr>')
        out = []
        for c in checklist:
            extra = "" if c["unreal_pct"] is None else f'{c["unreal_pct"]:+.1f}%'
            etf_tag = '<span class="tag book">ETF</span> ' if c.get("is_etf") else ""
            out.append(
                f'<tr><td><span class="tag {c["level"]}">{c["level"].upper()}</span></td>'
                f'<td>{etf_tag}<b>{c["symbol"]}</b></td>'
                f'<td><span class="tag book">{c["book"]}</span> '
                f'<span class="{fc.color_of(c["unreal_pct"] or 0)}">{extra}</span></td>'
                f'<td>{c["msg"]}</td></tr>')
        return "".join(out)

    # ── Desk roll-call ──
    def roll_rows():
        out = []
        for r in roll_call:
            dot = {"alert": "alert", "watch": "watch", "ok": "ok"}.get(r["level"], "book")
            age = f'<span class="{"neg" if r["stale"] else "sub"}">{r["age_label"]}' \
                  f'{" · stale" if (r["stale"] and r["filed"]) else ""}</span>'
            out.append(
                f'<tr><td><span class="tag {dot}">{r["level"].upper()}</span></td>'
                f'<td><b>{r["name"]}</b></td>'
                f'<td>{r["headline"]}</td>'
                f'<td>{age}</td>'
                f'<td><a href="{r["page"]}">open →</a></td></tr>')
        return "".join(out)

    body = f"""
  {banner}
  {stats}

  <h2>ETF Lens — Fresh Ideas</h2>
  {idea_banner}
  <div class="card"><table>
    <tr><th>ETF</th><th>Rank</th><th>Momentum</th><th>Entry</th>
        <th>Stop / Target</th><th>Why</th></tr>
    {idea_rows()}
  </table></div>

  <h2>ETF Leaderboard</h2>
  <div class="card"><table>
    <tr><th>#</th><th>ETF</th><th>Price</th><th>Score</th><th>Drivers</th></tr>
    {board_rows()}
  </table></div>

  <h2>Held ETF Health <span class="sub">(ETFs you own, both books)</span></h2>
  <div class="card"><table>
    <tr><th>ETF</th><th>Book</th><th>Standing</th><th>Unrealized</th><th>Read</th></tr>
    {health_rows()}
  </table></div>

  <h2>Fund Risk <span class="sub">(Sarah's rules, every position)</span></h2>
  <div class="card"><table>
    <tr><th>Priority</th><th>Symbol</th><th>Book / P&amp;L</th><th>What Houston sees</th></tr>
    {checklist_rows()}
  </table></div>

  <h2>Desk Roll-Call <span class="sub">(each desk's last filed report)</span></h2>
  <div class="card"><table>
    <tr><th>State</th><th>Desk</th><th>Latest report</th><th>Age</th><th></th></tr>
    {roll_rows()}
  </table></div>
  <p class="sub" style="margin-top:8px">Alex (Analyst) and Marcus (Flow) are
  stateless desks — they recompute on their own pages and file nothing to main,
  so they don't appear on the roll-call. Houston covers the ETF slice of Alex's
  watchlist above.</p>
"""
    return fc.page("Houston — Mission Control", "houston.html",
                   "The coordinator: every desk reports in, one ETF-led read comes out. "
                   "Advisory only — never trades.",
                   updated, body)


def render_email(ideas, checklist, roll_call, combined_pnl, n_alert, n_watch, updated):
    top_etf = ideas[0]["ticker"] if ideas else None
    tone, _, msg = _posture(n_alert, n_watch, roll_call, top_etf)

    # ETF idea line
    if ideas:
        top = ideas[0]
        idea_html = (f'<p style="font-size:14px;margin:0 0 12px"><b>Top ETF idea:</b> '
                     f'{top["ticker"]} — {top["name"]} · momentum {top["score"]}<br>'
                     f'<span style="color:#475569;font-size:12.5px">entry '
                     f'${top["plan"]["entry"]:.2f} · stop ${top["plan"]["stop"]:.2f} · '
                     f'target ${top["plan"]["target"]:.2f} · {top["thesis"]}</span></p>')
    else:
        idea_html = ('<p style="color:#475569;font-size:13.5px">No unheld ETF cleared the '
                     'momentum threshold today.</p>')

    # Risk items
    if checklist:
        items = ""
        for c in checklist[:8]:
            color = "#dc2626" if c["level"] == "alert" else "#b45309"
            items += (f'<li style="margin-bottom:5px"><b style="color:{color}">'
                      f'{c["level"].upper()}</b> · <b>{c["symbol"]}</b> '
                      f'<span style="color:#94a3b8">({c["book"]})</span> — {c["msg"]}</li>')
        risk_html = f'<ul style="margin:0 0 14px;padding-left:18px;font-size:13px">{items}</ul>'
    else:
        risk_html = ('<p style="color:#166534;background:#f0fdf4;border:1px solid #bbf7d0;'
                     'border-radius:8px;padding:10px 12px;font-size:13px">Risk all clear across '
                     'both books.</p>')

    # Desk roll-call
    rows = ""
    for r in roll_call:
        color = {"alert": "#dc2626", "watch": "#b45309", "ok": "#166534"}.get(r["level"], "#475569")
        age = r["age_label"] + (" · stale" if (r["stale"] and r["filed"]) else "")
        rows += (f'<tr><td style="padding:5px 8px"><b>{r["name"]}</b></td>'
                 f'<td style="padding:5px 8px;color:#334155">{r["headline"]}</td>'
                 f'<td style="padding:5px 8px;color:{color}">{age}</td></tr>')
    roll_html = (f'<table style="width:100%;border-collapse:collapse;font-size:12.5px">'
                 f'<tr style="color:#64748b;text-align:left">'
                 f'<th style="padding:5px 8px">Desk</th>'
                 f'<th style="padding:5px 8px">Latest report</th>'
                 f'<th style="padding:5px 8px">Age</th></tr>{rows}</table>')

    inner = (f'<p style="font-size:14px;margin:0 0 12px;color:#334155">{msg}</p>'
             f'<p style="font-size:14px;margin:0 0 12px"><b>Combined P&amp;L (both books):</b> '
             f'<b style="color:{"#166534" if combined_pnl >= 0 else "#dc2626"}">'
             f'${combined_pnl:,.0f}</b></p>'
             f'{idea_html}'
             f'<h3 style="font-size:13px;color:#64748b;text-transform:uppercase;'
             f'letter-spacing:.04em;margin:16px 0 6px">Fund Risk</h3>{risk_html}'
             f'<h3 style="font-size:13px;color:#64748b;text-transform:uppercase;'
             f'letter-spacing:.04em;margin:16px 0 6px">Desk Roll-Call</h3>{roll_html}')

    headline = (f"{n_alert} alert{'s' if n_alert != 1 else ''}" if n_alert
                else (f"{n_watch} on watch" if n_watch else "all clear"))
    etf_bit = f" · top ETF {top_etf}" if top_etf else ""
    subject = f"🛰️ Houston (Mission Control) — {headline}{etf_bit}"
    html = fc.email_shell("Houston · Mission Control", "daily brief", updated, inner,
                          f"{fc.BASE_URL}/houston.html")
    return html, subject


if __name__ == "__main__":
    run()
