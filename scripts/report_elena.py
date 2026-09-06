#!/usr/bin/env python3
"""
Elena — the reporter. Writes the weekly performance report.

Runs once a week, after Friday's close. Elena pulls together both books
(My Picks + Momentum) into one picture:

  * a combined P&L headline and return on capital deployed, versus SPY buy-and-hold
  * this week's change, drawn from the daily snapshots Sarah persists
  * a per-book breakdown — the Momentum paper portfolio's own return, win rate and
    equity curve, and the My Picks book's realized + unrealized standing
  * the week's biggest contributors and detractors across everything you hold

Elena reports the numbers as they are. She doesn't trade, and she doesn't flatter
the strategy — a losing week is a losing week.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fund_common as fc

CONFIG_PATH = fc.CONFIG / "report_elena.yml"
SLUG = "report_elena"


def _forward_fill(series_map, dates):
    """Forward-fill a {date: value} map across an ordered list of dates."""
    out, last = {}, 0.0
    for d in dates:
        if d in series_map and series_map[d] is not None:
            last = series_map[d]
        out[d] = last
    return out


def build_combined_curve(momentum_book, mp_curve):
    """
    Combined P&L curve across both books. Each series is forward-filled over the
    union of snapshot dates so a day one book didn't snapshot doesn't zero it out.
    Returns (rows, bench_by_date) where rows = [{date, mom_pnl, mp_pnl, combined}].
    """
    starting = momentum_book["starting"] if momentum_book else 0.0
    mom = {r["snap_date"]: (r["total_equity"] - starting) for r in (
        momentum_book["curve"] if momentum_book else [])}
    mp = {r["snap_date"]: r["total_pnl"] for r in mp_curve}
    bench = {}
    for r in (momentum_book["curve"] if momentum_book else []):
        if r.get("benchmark_price"):
            bench[r["snap_date"]] = r["benchmark_price"]
    for r in mp_curve:
        bench.setdefault(r["snap_date"], r.get("benchmark_price"))

    dates = sorted(set(mom) | set(mp))
    if not dates:
        return [], {}
    mom_ff = _forward_fill(mom, dates)
    mp_ff = _forward_fill(mp, dates)
    rows = [{"date": d, "mom_pnl": mom_ff[d], "mp_pnl": mp_ff[d],
             "combined": mom_ff[d] + mp_ff[d]} for d in dates]
    return rows, bench


def _week_delta(rows):
    """Combined P&L change over the last 7 calendar days (or since inception)."""
    if not rows:
        return 0.0, None
    last = rows[-1]
    try:
        cutoff = date.fromisoformat(last["date"]) - timedelta(days=7)
    except ValueError:
        return 0.0, None
    prior = None
    for r in rows:
        try:
            if date.fromisoformat(r["date"]) <= cutoff:
                prior = r
        except ValueError:
            continue
    base = prior if prior else rows[0]
    return round(last["combined"] - base["combined"], 2), base["date"]


def run():
    cfg = fc.load_yaml(CONFIG_PATH, {})
    top_movers = int(cfg.get("top_movers", 5))
    holdings = fc.load_holdings()
    benchmark = holdings["benchmark"]

    stub = fc.read_momentum_book({})
    mom_syms = [p["symbol"] for p in stub["positions"]] if stub else []
    my_syms = [p["symbol"] for p in holdings["open"]]

    print(f"Elena: pricing {len(my_syms)} My Picks + {len(mom_syms)} Momentum + {benchmark}...")
    prices = fc.fetch_prices(my_syms + mom_syms + [benchmark])

    my_book = fc.mark_my_picks(holdings, prices)
    momentum_book = fc.read_momentum_book(prices)
    bench_px = fc.last_price(prices, benchmark)

    # Keep the snapshot fresh even if Sarah didn't run today.
    fc.snapshot_my_picks(my_book, bench_px)
    mp_curve = fc.my_picks_curve()

    rows, bench = build_combined_curve(momentum_book, mp_curve)
    week_pnl, week_from = _week_delta(rows)

    combined_pnl = my_book["total_pnl"] + (momentum_book["total_pnl"] if momentum_book else 0.0)
    capital = (momentum_book["starting"] if momentum_book else 0.0) + my_book["cost_basis"]
    combined_return = round(combined_pnl / capital * 100, 2) if capital else 0.0

    # SPY buy-and-hold over the reporting window.
    bench_return = None
    dated = [r["date"] for r in rows if bench.get(r["date"])]
    if len(dated) >= 2:
        b0, b1 = bench[dated[0]], bench[dated[-1]]
        if b0:
            bench_return = round((b1 / b0 - 1) * 100, 2)

    contributors = _contributors(my_book, momentum_book, top_movers)

    updated = fc.now_et_str()
    dashboard = render_dashboard(my_book, momentum_book, rows, combined_pnl, combined_return,
                                 capital, week_pnl, week_from, bench_return, benchmark,
                                 contributors, updated)
    email_html, subject = render_email(combined_pnl, combined_return, week_pnl,
                                        my_book, momentum_book, bench_return, benchmark,
                                        contributors, updated)
    fc.write_agent_outputs(SLUG, dashboard, email_html, subject)
    fc.write_runlog(SLUG, {
        "combined_pnl": combined_pnl, "combined_return_pct": combined_return,
        "week_pnl": week_pnl, "week_from": week_from, "spy_return_pct": bench_return,
        "my_picks_pnl": my_book["total_pnl"],
        "momentum_pnl": momentum_book["total_pnl"] if momentum_book else None,
    })
    print(f"Elena done. Combined P&L {fc.money(combined_pnl)} "
          f"({combined_return:+.1f}%). Subject: {subject}")


def _contributors(my_book, momentum_book, n):
    items = []
    for p in my_book["positions"]:
        items.append({"symbol": p["symbol"], "book": "My Picks", "kind": "open",
                      "pnl": p["unreal"]})
    for c in my_book["closed"]:
        items.append({"symbol": c["symbol"], "book": "My Picks", "kind": "closed",
                      "pnl": c["pnl"]})
    if momentum_book:
        for p in momentum_book["positions"]:
            items.append({"symbol": p["symbol"], "book": "Momentum", "kind": "open",
                          "pnl": p["unreal"]})
        for t in momentum_book["trades"]:
            items.append({"symbol": t["symbol"], "book": "Momentum", "kind": "closed",
                          "pnl": t["pnl"]})
    winners = sorted([i for i in items if i["pnl"] > 0], key=lambda x: -x["pnl"])[:n]
    losers = sorted([i for i in items if i["pnl"] < 0], key=lambda x: x["pnl"])[:n]
    return {"winners": winners, "losers": losers}


# ─── RENDERING ────────────────────────────────────────────────────────────────

def _sparkline(rows, width=680, height=120):
    if len(rows) < 2:
        return '<div class="empty">The P&amp;L curve appears after a couple of snapshots.</div>'
    vals = [r["combined"] for r in rows]
    lo, hi = min(vals + [0.0]), max(vals + [0.0])
    span = (hi - lo) or 1
    pts = []
    for i, v in enumerate(vals):
        x = i / (len(vals) - 1) * width
        y = height - (v - lo) / span * (height - 12) - 6
        pts.append(f"{x:.1f},{y:.1f}")
    zero_y = height - (0 - lo) / span * (height - 12) - 6
    color = "#22c55e" if vals[-1] >= 0 else "#ef4444"
    return (f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
            f'style="width:100%;height:{height}px">'
            f'<line x1="0" y1="{zero_y:.1f}" x2="{width}" y2="{zero_y:.1f}" '
            f'stroke="#334155" stroke-width="1" stroke-dasharray="3 3"/>'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(pts)}"/>'
            f'</svg><div class="sub" style="margin-top:6px">Combined P&amp;L across both books '
            f'· dashed line = breakeven</div>')


def render_dashboard(my_book, momentum_book, rows, combined_pnl, combined_return,
                     capital, week_pnl, week_from, bench_return, benchmark,
                     contributors, updated):
    beat = ""
    if bench_return is not None:
        diff = combined_return - bench_return
        beat = (f'<div class="stat"><div class="lbl">vs {benchmark}</div>'
                f'<div class="val {fc.color_of(diff)}">{diff:+.1f} pts</div>'
                f'<div class="sub">{benchmark} {bench_return:+.1f}% since inception</div></div>')

    week_note = f" since {week_from}" if week_from else ""
    stats = f"""
  <div class="stats">
    <div class="stat"><div class="lbl">Combined P&amp;L</div>
      <div class="val {fc.color_of(combined_pnl)}">{fc.money(combined_pnl)}</div>
      <div class="sub">on {fc.money(capital)} deployed</div></div>
    <div class="stat"><div class="lbl">Return on Capital</div>
      <div class="val {fc.color_of(combined_return)}">{combined_return:+.1f}%</div>
      <div class="sub">both books combined</div></div>
    <div class="stat"><div class="lbl">This Week</div>
      <div class="val {fc.color_of(week_pnl)}">{fc.money(week_pnl)}</div>
      <div class="sub">change{week_note}</div></div>
    {beat}
  </div>"""

    # Per-book cards.
    mp = my_book
    mp_card = f"""
    <div class="stat"><div class="lbl">My Picks</div>
      <div class="val {fc.color_of(mp['total_pnl'])}">{fc.money(mp['total_pnl'])}</div>
      <div class="sub">{mp['return_pct']:+.1f}% on cost · {mp['n_open']} open · {mp['n_closed']} closed</div>
      <div class="sub">unreal {fc.money(mp['unrealized'])} · real {fc.money(mp['realized'])}</div></div>"""
    if momentum_book:
        mb = momentum_book
        wins = [t for t in mb["trades"] if t["pnl"] > 0]
        wr = len(wins) / len(mb["trades"]) * 100 if mb["trades"] else 0
        mom_card = f"""
    <div class="stat"><div class="lbl">Momentum (paper)</div>
      <div class="val {fc.color_of(mb['total_pnl'])}">{fc.money(mb['total_pnl'])}</div>
      <div class="sub">{mb['return_pct']:+.1f}% · equity {fc.money(mb['total_equity'])} · {mb['n_open']} open</div>
      <div class="sub">{mb['n_closed']} closed · win rate {wr:.0f}%</div></div>"""
    else:
        mom_card = ('<div class="stat"><div class="lbl">Momentum (paper)</div>'
                    '<div class="val">—</div><div class="sub">no ledger yet</div></div>')

    def mover_rows(movers, positive):
        if not movers:
            return f'<tr><td colspan="4" class="empty">No {"gainers" if positive else "losers"} this period.</td></tr>'
        out = []
        for m in movers:
            out.append(
                f'<tr><td><b>{m["symbol"]}</b></td>'
                f'<td><span class="tag book">{m["book"]}</span></td>'
                f'<td class="sub">{m["kind"]}</td>'
                f'<td class="{fc.color_of(m["pnl"])}">{fc.money(m["pnl"])}</td></tr>')
        return "".join(out)

    body = f"""
  {stats}
  <h2>Both Books</h2>
  <div class="stats">{mp_card}{mom_card}</div>

  <h2>Combined P&amp;L Curve</h2>
  <div class="card" style="padding:14px 16px">{_sparkline(rows)}</div>

  <h2>Top Contributors</h2>
  <div class="card"><table>
    <tr><th>Symbol</th><th>Book</th><th>Status</th><th>P&amp;L</th></tr>
    {mover_rows(contributors["winners"], True)}
  </table></div>

  <h2>Top Detractors</h2>
  <div class="card"><table>
    <tr><th>Symbol</th><th>Book</th><th>Status</th><th>P&amp;L</th></tr>
    {mover_rows(contributors["losers"], False)}
  </table></div>
"""
    return fc.page("Elena — Weekly Report", "report_elena.html",
                   "Combines both books into one weekly performance report.",
                   updated, body)


def render_email(combined_pnl, combined_return, week_pnl, my_book, momentum_book,
                 bench_return, benchmark, contributors, updated):
    color = "#16a34a" if combined_pnl >= 0 else "#dc2626"
    bench_line = ""
    if bench_return is not None:
        bench_line = (f' · vs {benchmark} {bench_return:+.1f}% '
                      f'({combined_return - bench_return:+.1f} pts)')

    mp = my_book
    mom_txt = "no ledger yet"
    if momentum_book:
        mb = momentum_book
        mom_txt = f"{fc.money(mb['total_pnl'])} ({mb['return_pct']:+.1f}%)"

    def mv(movers, sign):
        if not movers:
            return "<li>—</li>"
        return "".join(
            f'<li><b>{m["symbol"]}</b> <span style="color:#94a3b8">({m["book"]})</span> '
            f'<b style="color:{"#16a34a" if m["pnl"]>=0 else "#dc2626"}">{fc.money(m["pnl"])}</b></li>'
            for m in movers)

    inner = f"""
      <div style="font-size:26px;font-weight:800;color:{color}">
        {fc.money(combined_pnl)} <span style="font-size:15px">({combined_return:+.1f}%)</span></div>
      <p style="color:#64748b;margin:2px 0 16px;font-size:13px">
        This week {fc.money(week_pnl)}{bench_line}</p>
      <table style="width:100%;border-collapse:collapse;font-size:13.5px;margin-bottom:16px">
        <tr><td style="padding:6px 8px;color:#64748b">My Picks</td>
            <td style="padding:6px 8px"><b>{fc.money(mp['total_pnl'])}</b> ({mp['return_pct']:+.1f}% on cost,
            {mp['n_open']} open / {mp['n_closed']} closed)</td></tr>
        <tr><td style="padding:6px 8px;color:#64748b">Momentum</td>
            <td style="padding:6px 8px"><b>{mom_txt}</b></td></tr>
      </table>
      <p style="margin:0 0 4px;font-weight:600">Top contributors</p>
      <ul style="margin:0 0 12px;padding-left:18px;font-size:13px">{mv(contributors["winners"], 1)}</ul>
      <p style="margin:0 0 4px;font-weight:600">Top detractors</p>
      <ul style="margin:0 0 12px;padding-left:18px;font-size:13px">{mv(contributors["losers"], -1)}</ul>"""

    subject = (f"📊 Elena (Weekly) — {fc.money(combined_pnl)} ({combined_return:+.1f}%) · "
               f"week {fc.money(week_pnl)}")
    html = fc.email_shell("Elena · Weekly Report", "both books", updated, inner,
                          f"{fc.BASE_URL}/report_elena.html")
    return html, subject


if __name__ == "__main__":
    run()
