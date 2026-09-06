#!/usr/bin/env python3
"""
Sarah — the risk manager. Checks over open positions each day before the close.

Runs once a day, shortly before the bell. Sarah marks every open position in both
books (My Picks + Momentum) to market and applies a fixed set of risk rules:

  * stop breached / sitting just above the stop
  * target reached / within reach
  * an outsized unrealized loss that deserves a thesis review
  * dead money — flat for weeks
  * single-name concentration across the whole fund
  * how deep the Momentum book is drawn down from its peak

She ranks what she finds — act-now "alerts" above keep-an-eye "watch" items — into
a short pre-close checklist, and snapshots the My Picks book so Elena has a weekly
history to chart. Sarah recommends; she never closes a position for you.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fund_common as fc

CONFIG_PATH = fc.CONFIG / "risk_sarah.yml"
SLUG = "risk_sarah"


def run():
    cfg = fc.load_yaml(CONFIG_PATH, {})
    holdings = fc.load_holdings()
    benchmark = holdings["benchmark"]

    # Discover Momentum symbols (fallback-priced) so we can fetch everything at once.
    stub = fc.read_momentum_book({})
    mom_syms = [p["symbol"] for p in stub["positions"]] if stub else []
    my_syms = [p["symbol"] for p in holdings["open"]]

    print(f"Sarah: pricing {len(my_syms)} My Picks + {len(mom_syms)} Momentum + {benchmark}...")
    prices = fc.fetch_prices(my_syms + mom_syms + [benchmark])

    my_book = fc.mark_my_picks(holdings, prices)
    momentum_book = fc.read_momentum_book(prices)
    bench_px = fc.last_price(prices, benchmark)

    all_positions = list(my_book["positions"]) + (
        momentum_book["positions"] if momentum_book else [])
    total_exposure = my_book["market_value"] + (
        momentum_book["positions_value"] if momentum_book else 0.0)

    # ── Per-position flags ──
    reviewed = []
    for pos in all_positions:
        flags = fc.position_flags(pos, cfg)
        reviewed.append({"pos": pos, "flags": flags})

    # ── Fund-level flags ──
    conc = fc.concentration_flags(all_positions, total_exposure, cfg)
    conc_by_sym = {c["symbol"]: c for c in conc}
    for r in reviewed:
        c = conc_by_sym.get(r["pos"]["symbol"])
        if c:
            r["flags"].append(c)

    mom_dd = fc.drawdown_from_peak(
        [row["total_equity"] for row in momentum_book["curve"]]) if momentum_book else 0.0
    dd_alert = float(cfg.get("drawdown_alert_pct", 10.0))
    fund_flags = []
    if momentum_book and mom_dd <= -dd_alert:
        fund_flags.append({"level": "alert", "code": "drawdown",
                           "msg": f"Momentum book {mom_dd:.1f}% off its peak "
                                  f"(alert at −{dd_alert:.0f}%)"})

    # ── Rank the checklist: alerts first, then watches ──
    checklist = []
    for r in reviewed:
        for f in r["flags"]:
            checklist.append({**f, "symbol": r["pos"]["symbol"], "book": r["pos"]["book"],
                              "unreal_pct": r["pos"]["unreal_pct"], "price": r["pos"]["price"]})
    checklist += [{**f, "symbol": "FUND", "book": "—", "unreal_pct": None, "price": None}
                  for f in fund_flags]
    order = {"alert": 0, "watch": 1}
    checklist.sort(key=lambda x: (order.get(x["level"], 2), x["symbol"]))
    n_alert = sum(1 for c in checklist if c["level"] == "alert")
    n_watch = sum(1 for c in checklist if c["level"] == "watch")

    # ── Persist the daily My Picks snapshot for Elena ──
    fc.snapshot_my_picks(my_book, bench_px)

    updated = fc.now_et_str()
    dashboard = render_dashboard(checklist, reviewed, my_book, momentum_book,
                                 mom_dd, n_alert, n_watch, updated)
    email_html, subject = render_email(checklist, my_book, momentum_book,
                                       n_alert, n_watch, updated)
    fc.write_agent_outputs(SLUG, dashboard, email_html, subject)
    fc.write_runlog(SLUG, {
        "positions_reviewed": len(all_positions),
        "alerts": n_alert, "watches": n_watch,
        "momentum_drawdown_pct": mom_dd,
        "items": [f'{c["level"]}:{c["symbol"]}:{c["code"]}' for c in checklist],
    })
    print(f"Sarah done. {n_alert} alerts, {n_watch} watches. Subject: {subject}")


# ─── RENDERING ────────────────────────────────────────────────────────────────

def _posture(n_alert, n_watch, n_positions):
    if n_positions == 0:
        return ("flat", "book",
                "No open positions in either book yet. Add yours in config/my_picks.yml.")
    if n_alert:
        return ("alert", "alert",
                f"{n_alert} position{'s' if n_alert != 1 else ''} need attention before the close.")
    if n_watch:
        return ("flat", "watch",
                f"Nothing urgent — {n_watch} item{'s' if n_watch != 1 else ''} on watch.")
    return ("calm", "ok", "All clear. No stops, targets, or risk limits tripped.")


def render_dashboard(checklist, reviewed, my_book, momentum_book,
                     mom_dd, n_alert, n_watch, updated):
    n_positions = len(reviewed)
    tone, tag, msg = _posture(n_alert, n_watch, n_positions)
    banner = f'<div class="banner {tone}"><span class="tag {tag}">PRE-CLOSE</span>{msg}</div>'

    total_pnl = my_book["total_pnl"] + (momentum_book["total_pnl"] if momentum_book else 0.0)
    mom_ret = momentum_book["return_pct"] if momentum_book else None
    stats = f"""
  <div class="stats">
    <div class="stat"><div class="lbl">Open Positions</div><div class="val">{n_positions}</div>
      <div class="sub">{my_book['n_open']} My Picks · {momentum_book['n_open'] if momentum_book else 0} Momentum</div></div>
    <div class="stat"><div class="lbl">Alerts</div>
      <div class="val {'neg' if n_alert else 'pos'}">{n_alert}</div>
      <div class="sub">{n_watch} on watch</div></div>
    <div class="stat"><div class="lbl">Combined P&amp;L</div>
      <div class="val {fc.color_of(total_pnl)}">{fc.money(total_pnl)}</div>
      <div class="sub">unrealized + realized</div></div>
    <div class="stat"><div class="lbl">Momentum Drawdown</div>
      <div class="val {'neg' if mom_dd < -5 else ''}">{mom_dd:.1f}%</div>
      <div class="sub">from peak{'' if mom_ret is None else f' · {mom_ret:+.1f}% total'}</div></div>
  </div>"""

    def checklist_rows():
        if not checklist:
            return ('<tr><td colspan="4" class="empty">Nothing flagged. '
                    'Every position is inside its risk limits.</td></tr>')
        out = []
        for c in checklist:
            extra = "" if c["unreal_pct"] is None else f'{c["unreal_pct"]:+.1f}%'
            out.append(
                f'<tr><td><span class="tag {c["level"]}">{c["level"].upper()}</span></td>'
                f'<td><b>{c["symbol"]}</b></td>'
                f'<td><span class="tag book">{c["book"]}</span> '
                f'<span class="{fc.color_of(c["unreal_pct"] or 0)}">{extra}</span></td>'
                f'<td>{c["msg"]}</td></tr>')
        return "".join(out)

    def position_rows():
        if not reviewed:
            return '<tr><td colspan="7" class="empty">No open positions.</td></tr>'
        out = []
        for r in sorted(reviewed, key=lambda x: x["pos"]["book"]):
            p = r["pos"]
            worst = "alert" if any(f["level"] == "alert" for f in r["flags"]) else (
                "watch" if r["flags"] else "ok")
            state = {"alert": "⚠ act", "watch": "◔ watch", "ok": "✓ ok"}[worst]
            stop = f'${p["stop"]:.2f}' if p.get("stop") else "—"
            tgt = f'${p["target"]:.2f}' if p.get("target") else "—"
            dh = f'{p["days_held"]}d' if p.get("days_held") is not None else "—"
            out.append(
                f'<tr><td><b>{p["symbol"]}</b></td>'
                f'<td><span class="tag book">{p["book"]}</span></td>'
                f'<td>${p["price"]:.2f}</td><td>{stop} / {tgt}</td>'
                f'<td class="{fc.color_of(p["unreal_pct"])}">{p["unreal_pct"]:+.1f}%</td>'
                f'<td class="sub">{dh}</td>'
                f'<td class="{"neg" if worst=="alert" else ("sub" if worst=="watch" else "pos")}">{state}</td></tr>')
        return "".join(out)

    body = f"""
  {banner}
  {stats}
  <h2>Pre-Close Checklist</h2>
  <div class="card"><table>
    <tr><th>Priority</th><th>Symbol</th><th>Book / P&amp;L</th><th>What Sarah sees</th></tr>
    {checklist_rows()}
  </table></div>

  <h2>All Open Positions</h2>
  <div class="card"><table>
    <tr><th>Symbol</th><th>Book</th><th>Last</th><th>Stop / Target</th>
        <th>Unrealized</th><th>Held</th><th>Status</th></tr>
    {position_rows()}
  </table></div>
"""
    return fc.page("Sarah — Risk", "risk_sarah.html",
                   "Checks open positions in both books before the close, every day.",
                   updated, body)


def render_email(checklist, my_book, momentum_book, n_alert, n_watch, updated):
    n_positions = my_book["n_open"] + (momentum_book["n_open"] if momentum_book else 0)
    _, _, msg = _posture(n_alert, n_watch, n_positions)

    if checklist:
        items = ""
        for c in checklist[:10]:
            color = "#dc2626" if c["level"] == "alert" else "#b45309"
            items += (f'<li style="margin-bottom:5px"><b style="color:{color}">'
                      f'{c["level"].upper()}</b> · <b>{c["symbol"]}</b> '
                      f'<span style="color:#94a3b8">({c["book"]})</span> — {c["msg"]}</li>')
        list_html = f'<ul style="margin:0 0 16px;padding-left:18px;font-size:13.5px">{items}</ul>'
    else:
        list_html = ('<p style="color:#166534;background:#f0fdf4;border:1px solid #bbf7d0;'
                     'border-radius:8px;padding:12px 14px">All clear — no stops, targets, or '
                     'risk limits tripped.</p>')

    headline = (f"{n_alert} alert{'s' if n_alert != 1 else ''}"
                if n_alert else (f"{n_watch} on watch" if n_watch else "all clear"))
    inner = (f'<p style="font-size:14px;margin:0 0 12px;color:#334155">{msg}</p>{list_html}')
    subject = f"🛡️ Sarah (Risk) — {headline} · {n_positions} open"
    html = fc.email_shell("Sarah · Risk", "pre-close", updated, inner,
                          f"{fc.BASE_URL}/risk_sarah.html")
    return html, subject


if __name__ == "__main__":
    run()
