#!/usr/bin/env python3
"""
Marcus — the flow trader. Scans options activity for big, aggressive trades.

Modeled on the WSJ "Codex options-flow" agent: sift options activity, score it
for size and aggression, surface the single highest-confidence setup, re-check it
against a criteria list, and show a DEFINED-RISK way to express it.

IMPORTANT — what the data can and can't do. The free path reads delayed
end-of-day OPTION-CHAIN snapshots from yfinance. From a chain you can compute the
classic "unusual activity" tells — volume vs open interest, premium notional,
days-to-expiry, moneyness — and that's what Marcus scores. What a chain CANNOT
show is the actual tape: sweeps, blocks, and which side hit the bid/ask. That is
the real "institutional flow", and it needs a paid feed. So the yfinance path is
an honest PROXY, labeled as such wherever it prints. Real providers (Polygon,
Unusual Whales) drop in behind the FlowProvider interface below.

Advisory only. Marcus flags setups; he never places an order. Long options can
lose 100% of premium — every suggestion here is framed as defined risk.
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fund_common as fc

CONFIG_PATH = fc.CONFIG / "flow_marcus.yml"
SLUG = "flow_marcus"


# ─── FLOW PROVIDER INTERFACE (phased data sources) ────────────────────────────

class FlowProvider:
    """
    A source of option-contract activity. Implementations return a flat list of
    contract dicts with at least: symbol, spot, type ('call'/'put'), strike,
    expiry (ISO), dte, last, bid, ask, volume, open_interest, iv.
    Scoring, criteria, and rendering are provider-agnostic and live below.
    """
    name = "base"

    def unusual_contracts(self, symbols, cfg):
        raise NotImplementedError


class YFinanceProvider(FlowProvider):
    """FREE proxy: delayed end-of-day option chains. No sweep/aggressor data."""
    name = "yfinance (delayed chains — proxy, not true flow)"

    def _spot(self, tkr):
        try:
            fi = getattr(tkr, "fast_info", None)
            if fi:
                px = fi.get("lastPrice") or fi.get("last_price")
                if px:
                    return float(px)
        except Exception:
            pass
        try:
            h = tkr.history(period="5d")
            if len(h):
                return float(h["Close"].dropna().iloc[-1])
        except Exception:
            pass
        return None

    def unusual_contracts(self, symbols, cfg):
        import yfinance as yf
        today = datetime.now(fc.ET).date()
        min_dte = int(cfg.get("min_dte", 3))
        max_dte = int(cfg.get("max_dte", 60))
        per_sym = int(cfg.get("expiries_per_symbol", 4))
        min_vol = float(cfg.get("min_contract_volume", 100))

        out = []
        for sym in symbols:
            try:
                tkr = yf.Ticker(sym)
                spot = self._spot(tkr)
                if not spot:
                    continue
                expiries = list(getattr(tkr, "options", []) or [])
            except Exception as e:
                print(f"  ! {sym}: {e}")
                continue

            picked = 0
            for exp in expiries:
                if picked >= per_sym:
                    break
                try:
                    dte = (date.fromisoformat(exp) - today).days
                except ValueError:
                    continue
                if dte < min_dte or dte > max_dte:
                    continue
                try:
                    chain = tkr.option_chain(exp)
                except Exception as e:
                    print(f"  ! {sym} {exp}: {e}")
                    continue
                picked += 1
                for df, typ in ((chain.calls, "call"), (chain.puts, "put")):
                    for _, r in df.iterrows():
                        vol = float(r.get("volume") or 0)
                        if vol < min_vol:
                            continue
                        out.append(_contract(
                            symbol=sym, spot=spot, typ=typ, strike=float(r["strike"]),
                            expiry=exp, dte=dte, last=float(r.get("lastPrice") or 0),
                            bid=float(r.get("bid") or 0), ask=float(r.get("ask") or 0),
                            volume=vol, open_interest=float(r.get("openInterest") or 0),
                            iv=float(r.get("impliedVolatility") or 0)))
        return out


class PolygonProvider(FlowProvider):
    """Drop-in slot for real options flow via Polygon.io. Not wired yet."""
    name = "polygon"

    def unusual_contracts(self, symbols, cfg):
        raise NotImplementedError(
            "Polygon flow provider isn't wired yet. Implement unusual_contracts() "
            "here using the key in env $%s, or set data_source: yfinance."
            % cfg.get("api_key_env", "FLOW_API_KEY"))


class UnusualWhalesProvider(FlowProvider):
    """Drop-in slot for real options flow via Unusual Whales. Not wired yet."""
    name = "unusual_whales"

    def unusual_contracts(self, symbols, cfg):
        raise NotImplementedError(
            "Unusual Whales flow provider isn't wired yet. Implement "
            "unusual_contracts() here using the key in env $%s, or set "
            "data_source: yfinance." % cfg.get("api_key_env", "FLOW_API_KEY"))


_PROVIDERS = {
    "yfinance": YFinanceProvider,
    "polygon": PolygonProvider,
    "unusual_whales": UnusualWhalesProvider,
}


def get_provider(cfg):
    src = str(cfg.get("data_source", "yfinance")).lower()
    if src not in _PROVIDERS:
        raise ValueError(f"Unknown data_source '{src}'. "
                         f"Options: {', '.join(_PROVIDERS)}.")
    return _PROVIDERS[src]()


# ─── CONTRACT MODEL + PURE SCORING (provider-agnostic, unit-tested) ───────────

def _contract(symbol, spot, typ, strike, expiry, dte, last, bid, ask,
              volume, open_interest, iv):
    price = ask or last or bid or 0.0          # what you'd pay to get long
    notional = volume * price * 100
    vol_oi = (volume / open_interest) if open_interest > 0 else (volume and float("inf") or 0.0)
    # Signed OTM%: positive = out-of-the-money in the trade's direction.
    otm = (strike / spot - 1) if typ == "call" else (1 - strike / spot)
    return {
        "symbol": symbol, "spot": round(spot, 2), "type": typ, "strike": strike,
        "expiry": expiry, "dte": dte, "last": last, "bid": bid, "ask": ask,
        "price": round(price, 2), "volume": int(volume),
        "open_interest": int(open_interest), "iv": iv,
        "notional": notional, "vol_oi": vol_oi, "otm": otm,
    }


def score_contract(c):
    """
    Transparent, additive "how aggressive / unusual is this print" score. Every
    factor names its contribution so the board can explain the read. This scores
    the *shape* of the activity, not a directional forecast.
    Returns (score, factors[]).
    """
    score, factors = 0.0, []

    def add(pts, why):
        nonlocal score
        score += pts
        factors.append(f"{'+' if pts >= 0 else ''}{pts:.1f} {why}")

    # Volume vs open interest — the classic "new, aggressive positioning" tell.
    r = c["vol_oi"]
    if r == float("inf"):
        add(2.0, "volume with ~0 OI (brand-new)")
    elif r >= 5:
        add(3.0, f"vol {r:.1f}x OI (very fresh)")
    elif r >= 3:
        add(2.2, f"vol {r:.1f}x OI")
    elif r >= 1.5:
        add(1.4, f"vol {r:.1f}x OI (new positioning)")
    elif r >= 1:
        add(0.6, f"vol {r:.1f}x OI")
    else:
        add(-0.5, f"vol {r:.1f}x OI (likely closing)")

    # Premium notional — dollars at risk today = conviction/size.
    n = c["notional"]
    if n >= 2_000_000:
        add(2.5, f"${n/1e6:.1f}M premium")
    elif n >= 1_000_000:
        add(1.8, f"${n/1e6:.1f}M premium")
    elif n >= 500_000:
        add(1.2, f"${n/1e3:.0f}K premium")
    elif n >= 250_000:
        add(0.6, f"${n/1e3:.0f}K premium")

    # Absolute contract volume — liquidity behind the move.
    v = c["volume"]
    if v >= 5000:
        add(1.0, f"{v:,} contracts")
    elif v >= 2000:
        add(0.6, f"{v:,} contracts")
    elif v >= 1000:
        add(0.3, f"{v:,} contracts")

    # Days to expiry — near-dated momentum, but not 0-DTE lottery.
    d = c["dte"]
    if 5 <= d <= 30:
        add(1.0, f"{d} DTE (momentum window)")
    elif d < 5:
        add(-0.3, f"{d} DTE (very short)")
    elif d > 45:
        add(-0.3, f"{d} DTE (longer dated)")

    # Moneyness — near-to-moderately OTM is the classic directional chase.
    otm = c["otm"]
    if -0.02 <= otm <= 0.07:
        add(1.0, "near the money")
    elif 0.07 < otm <= 0.15:
        add(0.6, "moderately OTM")
    elif otm > 0.25:
        add(-0.6, "deep OTM (lotto)")
    elif otm < -0.10:
        add(-0.3, "deep ITM")

    return round(score, 2), factors


def passes_criteria(c, cfg):
    """Marcus's re-check: the hard gates a high-confidence trade must clear."""
    return (
        c["volume"] >= float(cfg.get("min_volume", 500))
        and c["vol_oi"] >= float(cfg.get("min_vol_oi_ratio", 1.5))
        and c["notional"] >= float(cfg.get("min_notional", 250000))
        and float(cfg.get("min_dte", 3)) <= c["dte"] <= float(cfg.get("max_dte", 60))
    )


def flow_sentiment(contracts):
    """Aggregate call vs put premium notional into a directional tilt per symbol."""
    by = {}
    for c in contracts:
        s = by.setdefault(c["symbol"], {"call": 0.0, "put": 0.0})
        s[c["type"]] += c["notional"]
    out = []
    for sym, s in by.items():
        total = s["call"] + s["put"]
        if total <= 0:
            continue
        call_pct = s["call"] / total * 100
        tilt = ("bullish" if call_pct >= 65 else
                "bearish" if call_pct <= 35 else "mixed")
        out.append({"symbol": sym, "call_notional": s["call"], "put_notional": s["put"],
                    "call_pct": round(call_pct, 0), "total": total, "tilt": tilt})
    out.sort(key=lambda x: -x["total"])
    return out


def defined_risk_play(c):
    """
    Frame the top pick as a single long option with EXPLICIT, capped risk.
    Max loss on a long option is 100% of premium — always shown.
    """
    debit_ps = c["price"]                       # per share
    debit = debit_ps * 100                       # per contract
    if c["type"] == "call":
        breakeven = c["strike"] + debit_ps
    else:
        breakeven = c["strike"] - debit_ps
    return {
        "debit_per_contract": round(debit, 2),
        "max_loss": round(debit, 2),             # = the debit; can go to -100%
        "breakeven": round(breakeven, 2),
        "note": ("Max loss is the premium paid (−100% if it expires worthless). "
                 "A vertical spread at the same strike caps cost further."),
    }


# ─── RUN ──────────────────────────────────────────────────────────────────────

def build_symbols(cfg):
    syms = [str(s).strip().upper() for s in (cfg.get("symbols") or []) if s]
    if cfg.get("include_holdings", True):
        holdings = fc.load_holdings()
        stub = fc.read_momentum_book({})
        syms += [p["symbol"] for p in holdings["open"]]
        if stub:
            syms += [p["symbol"] for p in stub["positions"]]
    # De-dupe, preserve order.
    seen, out = set(), []
    for s in syms:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def run():
    cfg = fc.load_yaml(CONFIG_PATH, {})
    provider = get_provider(cfg)
    symbols = build_symbols(cfg)
    top_n = int(cfg.get("top_n", 15))

    print(f"Marcus: scanning option chains for {len(symbols)} names "
          f"via {provider.name}...")

    error = None
    contracts = []
    try:
        contracts = provider.unusual_contracts(symbols, cfg)
    except NotImplementedError as e:
        error = str(e)
        print(f"  provider not available: {e}")
    except Exception as e:
        error = f"data unavailable: {e}"
        print(f"  fetch failed: {e}")

    scored = []
    for c in contracts:
        s, factors = score_contract(c)
        c["score"], c["factors"] = s, factors
        c["qualifies"] = passes_criteria(c, cfg)
        scored.append(c)
    scored.sort(key=lambda x: (-x["score"], -x["notional"]))

    board = scored[:top_n]
    qualified = [c for c in scored if c["qualifies"]]
    top_pick = qualified[0] if qualified else None
    play = defined_risk_play(top_pick) if top_pick else None
    sentiment = flow_sentiment(scored)

    # Decide whether this run is worth an email ("when needed"). Dashboard is
    # published every run regardless; only the email is gated.
    level = str(cfg.get("notify_level", "high_confidence")).lower()
    if level == "always":
        should_send = True
    elif level == "any_activity":
        should_send = len(scored) > 0
    else:  # "high_confidence" (default)
        should_send = top_pick is not None
    fc.write_send_flag(SLUG, should_send)

    updated = fc.now_et_str()
    is_proxy = str(cfg.get("data_source", "yfinance")).lower() == "yfinance"
    dashboard = render_dashboard(board, top_pick, play, sentiment, provider,
                                 is_proxy, error, updated)
    email_html, subject = render_email(board, top_pick, play, error, updated)
    fc.write_agent_outputs(SLUG, dashboard, email_html, subject)
    fc.write_runlog(SLUG, {
        "provider": provider.name, "symbols": len(symbols),
        "contracts_scanned": len(scored), "qualified": len(qualified),
        "top_pick": (f'{top_pick["symbol"]} {top_pick["strike"]}{top_pick["type"][0].upper()} '
                     f'{top_pick["expiry"]}' if top_pick else None),
        "error": error, "notify_level": level, "emailed": should_send,
    })
    n = f"{len(qualified)} qualified of {len(scored)}"
    print(f"Marcus done. {n}. Email: {'yes' if should_send else 'no (nothing needed)'}. "
          f"Subject: {subject}")


# ─── RENDERING ────────────────────────────────────────────────────────────────

def _oi_str(r):
    return "∞" if r == float("inf") else f"{r:.1f}x"


def _proxy_note(is_proxy):
    if not is_proxy:
        return ""
    return ('<div class="banner flat"><span class="tag book">PROXY</span>'
            'Source is delayed option-<b>chain</b> data (volume, OI, IV) — a proxy for '
            'flow. It can\'t see sweeps, blocks, or which side hit the bid/ask, so it '
            'can\'t truly confirm institutional intent. Wire a paid feed for that.</div>')


def render_dashboard(board, top_pick, play, sentiment, provider, is_proxy, error, updated):
    if error:
        banner = (f'<div class="banner flat"><span class="tag book">NO DATA</span>{error}</div>')
    elif top_pick:
        tp = top_pick
        arrow = "▲ calls" if tp["type"] == "call" else "▼ puts"
        banner = (
            f'<div class="banner calm"><span class="tag ok">HIGH-CONFIDENCE</span>'
            f'<b>{tp["symbol"]} ${tp["strike"]:g} {tp["type"].upper()}</b> · {tp["expiry"]} '
            f'({tp["dte"]}d) · {arrow} · score {tp["score"]}<br>'
            f'<span class="sub">{tp["volume"]:,} vol vs {tp["open_interest"]:,} OI '
            f'({_oi_str(tp["vol_oi"])}) · ${tp["notional"]/1e3:,.0f}K premium · '
            f'{" · ".join(tp["factors"][:5])}</span>'
            + (f'<div class="sub" style="margin-top:6px">Defined-risk: debit '
               f'≈ ${play["debit_per_contract"]:,.0f}/contract · '
               f'<b>max loss ${play["max_loss"]:,.0f} (−100%)</b> · '
               f'breakeven ${play["breakeven"]:.2f}. {play["note"]}</div>' if play else "")
            + '</div>')
    else:
        banner = ('<div class="banner flat"><span class="tag book">QUIET</span>'
                  'No contract cleared the high-confidence criteria today.</div>')

    def board_rows():
        if not board:
            return '<tr><td colspan="9" class="empty">No unusual option activity detected.</td></tr>'
        out = []
        for c in board:
            cp = "pos" if c["type"] == "call" else "neg"
            star = " ★" if c.get("qualifies") else ""
            out.append(
                f'<tr><td><b>{c["symbol"]}</b>{star}</td>'
                f'<td class="{cp}">{c["type"].upper()}</td>'
                f'<td>${c["strike"]:g}</td><td>{c["expiry"]}<div class="sub">{c["dte"]}d</div></td>'
                f'<td>{c["volume"]:,}</td><td>{c["open_interest"]:,}</td>'
                f'<td>{_oi_str(c["vol_oi"])}</td>'
                f'<td>${c["notional"]/1e3:,.0f}K</td>'
                f'<td><b>{c["score"]}</b><div class="sub">{" · ".join(c["factors"][:3])}</div></td></tr>')
        return "".join(out)

    def sentiment_rows():
        if not sentiment:
            return '<tr><td colspan="4" class="empty">—</td></tr>'
        out = []
        for s in sentiment[:12]:
            cls = {"bullish": "pos", "bearish": "neg", "mixed": "sub"}[s["tilt"]]
            out.append(
                f'<tr><td><b>{s["symbol"]}</b></td>'
                f'<td class="{cls}">{s["tilt"]} ({s["call_pct"]:.0f}% calls)</td>'
                f'<td>${s["call_notional"]/1e3:,.0f}K</td>'
                f'<td>${s["put_notional"]/1e3:,.0f}K</td></tr>')
        return "".join(out)

    body = f"""
  {_proxy_note(is_proxy)}
  {banner}
  <h2>Unusual Options Activity</h2>
  <div class="card"><table>
    <tr><th>Symbol</th><th>C/P</th><th>Strike</th><th>Expiry</th><th>Volume</th>
        <th>OI</th><th>Vol/OI</th><th>Premium</th><th>Score · why</th></tr>
    {board_rows()}
  </table></div>
  <div class="sub" style="margin:6px 2px">★ = clears the high-confidence criteria.</div>

  <h2>Flow Tilt <span class="sub">(call vs put premium by name)</span></h2>
  <div class="card"><table>
    <tr><th>Symbol</th><th>Tilt</th><th>Call premium</th><th>Put premium</th></tr>
    {sentiment_rows()}
  </table></div>

  <div class="disc" style="margin-top:20px"><b>Options are far riskier than the
  equity book.</b> A long option can lose 100% of its premium. Everything here is a
  delayed, chain-derived read — not a recommendation, and not confirmation of
  institutional flow. Source: {provider.name}.</div>
"""
    return fc.page("Marcus — Flow", "flow_marcus.html",
                   "Scans options activity for big, aggressive trades — advisory, defined-risk.",
                   updated, body)


def render_email(board, top_pick, play, error, updated):
    if error:
        inner = f'<p style="color:#475569">{error}</p>'
        subject = "🎯 Marcus (Flow) — no data this run"
    elif top_pick:
        tp = top_pick
        risk = (f'<br>Defined-risk: debit ≈ ${play["debit_per_contract"]:,.0f}/contract · '
                f'<b>max loss ${play["max_loss"]:,.0f} (−100%)</b> · '
                f'breakeven ${play["breakeven"]:.2f}' if play else "")
        rows = ""
        for c in board[:8]:
            rows += (f'<tr><td style="padding:6px 8px"><b>{c["symbol"]}</b> '
                     f'${c["strike"]:g}{c["type"][0].upper()}</td>'
                     f'<td style="padding:6px 8px">{c["expiry"]} ({c["dte"]}d)</td>'
                     f'<td style="padding:6px 8px">{_oi_str(c["vol_oi"])}</td>'
                     f'<td style="padding:6px 8px">${c["notional"]/1e3:,.0f}K</td>'
                     f'<td style="padding:6px 8px">{c["score"]}</td></tr>')
        inner = (
            f'<p style="font-size:15px;margin:0 0 10px"><b>High-confidence:</b> '
            f'{tp["symbol"]} ${tp["strike"]:g} {tp["type"].upper()} {tp["expiry"]} '
            f'({tp["dte"]}d) · score {tp["score"]}{risk}</p>'
            f'<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px">'
            f'<tr style="color:#64748b;text-align:left">'
            f'<th style="padding:6px 8px">Contract</th><th style="padding:6px 8px">Expiry</th>'
            f'<th style="padding:6px 8px">Vol/OI</th><th style="padding:6px 8px">Premium</th>'
            f'<th style="padding:6px 8px">Score</th></tr>{rows}</table>'
            f'<p style="color:#94a3b8;font-size:11px">Delayed option-chain proxy — not true '
            f'institutional flow. Long options can lose 100% of premium.</p>')
        subject = (f'🎯 Marcus (Flow) — {tp["symbol"]} ${tp["strike"]:g}{tp["type"][0].upper()} '
                   f'{tp["expiry"]} (score {tp["score"]})')
    else:
        inner = ('<p style="color:#475569">No contract cleared the high-confidence criteria '
                 'today. Nothing worth chasing.</p>')
        subject = "🎯 Marcus (Flow) — no high-confidence setup today"

    html = fc.email_shell("Marcus · Flow", "options", updated, inner,
                          f"{fc.BASE_URL}/flow_marcus.html")
    return html, subject


if __name__ == "__main__":
    run()
