#!/usr/bin/env python3
"""
Alex — the analyst. Scans the market for promising stocks and ETFs.

Runs twice a day (open and close). Alex ranks the whole scanner universe with the
same transparent, additive momentum engine the paper trader uses, then publishes a
short, opinionated watchlist: the top ideas he'd bring to the desk today, each with
a plain-language thesis and a suggested entry / stop / target plan.

Alex is aware of what you already hold in *both* books (My Picks + Momentum) so he
never re-pitches a name you own — instead he calls those out separately under
"Holdings health", flagging any position that has slipped down the leaderboard.

Advisory only. Alex proposes; he never places an order.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fund_common as fc
from momentum_trader import (
    momentum_score, plan_trade, fetch_history, display_name, LEVERAGED,
)
from scanner import US_STOCKS, US_ETFS, CA_STOCKS, CA_ETFS

CONFIG_PATH = fc.CONFIG / "analyst_alex.yml"
SLUG = "analyst_alex"


def build_universe(cfg):
    tickers = list(US_STOCKS)
    if cfg.get("include_etfs", True):
        tickers += US_ETFS
    if cfg.get("include_canada", True):
        tickers += CA_STOCKS
        if cfg.get("include_etfs", True):
            tickers += CA_ETFS
    if cfg.get("exclude_leveraged", True):
        tickers = [t for t in tickers if t not in LEVERAGED]
    seen, out = set(), []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _top_factors(factors, n=6):
    def mag(f):
        try:
            return abs(float(f.split()[0]))
        except (ValueError, IndexError):
            return 0.0
    return " · ".join(sorted(factors, key=mag, reverse=True)[:n])


def run():
    cfg = fc.load_yaml(CONFIG_PATH, {})
    top_n = int(cfg.get("top_n", 12))
    min_score = float(cfg.get("min_score", 4.0))
    benchmark = str(cfg.get("benchmark", "SPY")).upper()

    universe = build_universe(cfg)
    holdings = fc.load_holdings()

    # Fetch the universe plus any held names (they may live outside the universe)
    # plus the benchmark, in one pass.
    my_syms = [p["symbol"] for p in holdings["open"]]
    print(f"Alex: scanning {len(universe)} names + {len(my_syms)} held + {benchmark}...")
    prices = fetch_history(universe + my_syms + [benchmark])

    my_book = fc.mark_my_picks(holdings, prices)
    momentum_book = fc.read_momentum_book(prices)
    held = fc.held_symbols(my_book, momentum_book)

    bench_closes = prices[benchmark][0] if benchmark in prices else None

    # Rank the universe.
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
    rank_of = {r["ticker"]: i + 1 for i, r in enumerate(ranked)}

    # Top fresh ideas: highest scorers Alex doesn't already own.
    ideas = []
    for r in ranked:
        if r["ticker"] in held or r["score"] < min_score:
            continue
        plan = plan_trade(r["price"], r["closes"], _default_profile(cfg))
        ideas.append({
            "ticker": r["ticker"], "name": display_name(r["ticker"]),
            "score": r["score"], "price": r["price"], "rank": rank_of[r["ticker"]],
            "plan": plan, "thesis": _top_factors(r["factors"], 6),
        })
        if len(ideas) >= top_n:
            break

    # Holdings health: where do the names you own currently rank?
    health = []
    for pos in list(my_book["positions"]) + (momentum_book["positions"] if momentum_book else []):
        sym = pos["symbol"]
        r = rank_of.get(sym)
        sc = next((x["score"] for x in ranked if x["ticker"] == sym), None)
        verdict = "not scored"
        if sc is not None:
            if sc >= min_score:
                verdict = "still a leader" if r and r <= top_n else "still qualifies"
            else:
                verdict = "momentum fading — watch"
        health.append({"symbol": sym, "book": pos["book"], "rank": r, "score": sc,
                       "unreal_pct": pos["unreal_pct"], "verdict": verdict})

    updated = fc.now_et_str()
    dashboard = render_dashboard(ideas, ranked[:25], health, updated, min_score)
    email_html, subject = render_email(ideas, updated)
    fc.write_agent_outputs(SLUG, dashboard, email_html, subject)
    fc.write_runlog(SLUG, {
        "ranked": len(ranked), "ideas": [i["ticker"] for i in ideas],
        "held_skipped": sorted(held & set(rank_of)), "top_n": top_n, "min_score": min_score,
    })
    print(f"Alex done. {len(ideas)} fresh ideas. Subject: {subject}")


def _default_profile(cfg):
    """Alex borrows a moderate stop/target profile for his suggested plans."""
    return {
        "initial_stop_pct": float(cfg.get("plan_stop_pct", 0.08)),
        "target_r": float(cfg.get("plan_target_r", 2.5)),
    }


# ─── RENDERING ────────────────────────────────────────────────────────────────

def render_dashboard(ideas, leaderboard, health, updated, min_score):
    if ideas:
        top = ideas[0]
        banner = (f'<div class="banner calm"><span class="tag ok">TOP IDEA</span>'
                  f'<b>{top["ticker"]}</b> — {top["name"]} · momentum {top["score"]} '
                  f'(#{top["rank"]} of universe)<br>'
                  f'<span class="sub">entry ${top["plan"]["entry"]:.2f} · '
                  f'stop ${top["plan"]["stop"]:.2f} · target ${top["plan"]["target"]:.2f} · '
                  f'{top["thesis"]}</span></div>')
    else:
        banner = (f'<div class="banner flat"><span class="tag book">QUIET</span>'
                  f'No new name scored ≥ {min_score} today that you don\'t already own.</div>')

    def idea_rows():
        if not ideas:
            return '<tr><td colspan="6" class="empty">No fresh ideas above threshold.</td></tr>'
        out = []
        for x in ideas:
            out.append(
                f'<tr><td><b>{x["ticker"]}</b><div class="sub">{x["name"][:30]}</div></td>'
                f'<td>#{x["rank"]}</td><td><b>{x["score"]}</b></td>'
                f'<td>${x["plan"]["entry"]:.2f}</td>'
                f'<td>${x["plan"]["stop"]:.2f} / ${x["plan"]["target"]:.2f}</td>'
                f'<td class="sub">{x["thesis"]}</td></tr>')
        return "".join(out)

    def health_rows():
        if not health:
            return ('<tr><td colspan="5" class="empty">No open positions in either book yet. '
                    'Add yours in config/my_picks.yml.</td></tr>')
        out = []
        for h in health:
            rank = f'#{h["rank"]}' if h["rank"] else "—"
            sc = f'{h["score"]}' if h["score"] is not None else "—"
            cls = fc.color_of(h["unreal_pct"])
            warn = "watch" if "fading" in h["verdict"] else "sub"
            out.append(
                f'<tr><td><b>{h["symbol"]}</b></td>'
                f'<td><span class="tag book">{h["book"]}</span></td>'
                f'<td>{rank} · score {sc}</td>'
                f'<td class="{cls}">{h["unreal_pct"]:+.1f}%</td>'
                f'<td class="{warn}">{h["verdict"]}</td></tr>')
        return "".join(out)

    def board_rows():
        out = []
        for i, r in enumerate(leaderboard, 1):
            out.append(f'<tr><td>{i}</td><td><b>{r["ticker"]}</b></td>'
                       f'<td>${r["price"]:.2f}</td><td><b>{r["score"]}</b></td>'
                       f'<td class="sub">{_top_factors(r["factors"], 5)}</td></tr>')
        return "".join(out)

    body = f"""
  {banner}
  <h2>Today's Ideas</h2>
  <div class="card"><table>
    <tr><th>Symbol</th><th>Rank</th><th>Momentum</th><th>Entry</th>
        <th>Stop / Target</th><th>Why</th></tr>
    {idea_rows()}
  </table></div>

  <h2>Holdings Health <span class="sub">(names you already own, both books)</span></h2>
  <div class="card"><table>
    <tr><th>Symbol</th><th>Book</th><th>Standing</th><th>Unrealized</th><th>Read</th></tr>
    {health_rows()}
  </table></div>

  <h2>Universe Leaderboard</h2>
  <div class="card"><table>
    <tr><th>#</th><th>Symbol</th><th>Price</th><th>Score</th><th>Drivers</th></tr>
    {board_rows()}
  </table></div>
"""
    return fc.page("Alex — Analyst", "analyst_alex.html",
                   "Scans the market for promising stocks &amp; ETFs, twice a day.",
                   updated, body)


def render_email(ideas, updated):
    if ideas:
        rows = ""
        for x in ideas[:8]:
            rows += (
                f'<tr><td style="padding:6px 8px"><b>{x["ticker"]}</b>'
                f'<div style="color:#94a3b8;font-size:11px">{x["name"][:28]}</div></td>'
                f'<td style="padding:6px 8px">{x["score"]}</td>'
                f'<td style="padding:6px 8px">${x["plan"]["entry"]:.2f}</td>'
                f'<td style="padding:6px 8px">${x["plan"]["stop"]:.2f} / ${x["plan"]["target"]:.2f}</td>'
                f'</tr>')
        top = ideas[0]
        headline = f"{len(ideas)} ideas · top {top['ticker']} ({top['score']})"
        inner = (
            f'<p style="font-size:15px;margin:0 0 12px"><b>Top idea:</b> {top["ticker"]} — '
            f'{top["name"]}<br><span style="color:#475569;font-size:13px">{top["thesis"]}</span></p>'
            f'<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px">'
            f'<tr style="color:#64748b;text-align:left">'
            f'<th style="padding:6px 8px">Symbol</th><th style="padding:6px 8px">Momentum</th>'
            f'<th style="padding:6px 8px">Entry</th><th style="padding:6px 8px">Stop / Target</th></tr>'
            f'{rows}</table>')
    else:
        headline = "no fresh ideas today"
        inner = ('<p style="color:#475569">Nothing new cleared the momentum threshold today '
                 'that you don\'t already hold. Sitting on hands is a position too.</p>')

    subject = f"🔎 Alex (Analyst) — {headline}"
    html = fc.email_shell("Alex · Analyst", "watchlist", updated, inner,
                          f"{fc.BASE_URL}/analyst_alex.html")
    return html, subject


if __name__ == "__main__":
    run()
