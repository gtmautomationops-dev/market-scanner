"""Insider Radar dashboard and email HTML generation."""

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

SIGNAL_COLORS = {
    "STRONG BULLISH": "#1a7a3a",
    "BULLISH": "#4a9a5a",
    "NEUTRAL": "#8a8578",
    "CAUTION": "#b0413e",
    "OFFERING PARTICIPATION": "#6a6a8a",
}


def fetch_price_context(tickers):
    """52-week price position for a small set of tickers (the highlighted
    names). Bounded to highlights so this is one cheap batch call. Returns
    {ticker: {last, hi, lo, pos}} where pos is 0.0 (at 52w low) .. 1.0 (high).
    Best-effort: returns {} on any failure so the email still renders."""
    tickers = sorted({t for t in tickers if t})
    if not tickers:
        return {}
    out = {}
    try:
        import yfinance as yf
        data = yf.download(" ".join(tickers), period="1y", auto_adjust=True,
                           progress=False, threads=True, group_by="ticker")
        multi = len(tickers) > 1
        for t in tickers:
            try:
                if multi:
                    if t not in data.columns.get_level_values(0):
                        continue
                    hist = data[t]
                else:
                    hist = data
                closes = hist["Close"].dropna()
                if closes.empty:
                    continue
                last, hi, lo = float(closes.iloc[-1]), float(closes.max()), float(closes.min())
                rng = hi - lo
                out[t] = {"last": last, "hi": hi, "lo": lo,
                          "pos": (last - lo) / rng if rng > 0 else 0.5}
            except Exception:
                continue
    except Exception:
        pass
    return out


def _px_zone(px):
    if not px:
        return ""
    pos = px["pos"]
    if pos <= 0.25:
        return "near 52w low"
    if pos >= 0.75:
        return "near 52w high"
    return "mid-range"


def _px_label(px):
    if not px:
        return ""
    from_hi = (px["last"] / px["hi"] - 1) * 100 if px["hi"] else 0
    return f"${px['last']:,.2f} · {_px_zone(px)} ({from_hi:+.0f}% vs high)"


def _pct(x):
    return f"{x*100:+.1f}%" if x is not None else "n/a"


def scorecard_html(sc):
    """Signal scorecard block: forward return of past bullish signals vs SPY."""
    if not sc or sc.get("total_tracked", 0) == 0:
        return ""
    graded = sc.get("graded", 0)
    if graded == 0:
        return (
            "<div style='background:#eef0ea;border:1px solid #d8d0bf;border-radius:8px;"
            "padding:12px 14px;margin-bottom:20px;font-size:12px;color:#6a6a6a'>"
            f"<strong>Signal scorecard:</strong> tracking {sc['total_tracked']} bullish "
            f"signal(s); none have aged past {sc['min_age_days']} days yet. Grades vs SPY "
            "will appear as signals mature.</div>"
        )
    timing_bits = ""
    for k in ("opportunistic", "routine"):
        t = sc["by_timing"].get(k)
        if t:
            timing_bits += f" &nbsp; {k}: {_pct(t['avg_excess'])} (n={t['n']})"
    beat = sc["beat_spy_pct"]
    return (
        "<div style='background:#eef0ea;border:1px solid #d8d0bf;border-radius:8px;"
        "padding:12px 14px;margin-bottom:20px;font-size:12px;color:#4a4a4a'>"
        f"<strong>Signal scorecard</strong> (bullish flags graded ≥{sc['min_age_days']}d after filing, "
        f"forward return vs SPY):<br>"
        f"n={graded} &nbsp; avg excess vs SPY: <strong>{_pct(sc['avg_excess_vs_spy'])}</strong> "
        f"&nbsp; beat SPY: {beat*100:.0f}%{(' &nbsp;|' + timing_bits) if timing_bits else ''}<br>"
        f"<span style='color:#8a8578'>Small, provisional sample — measures whether these "
        f"signals actually add edge. Not a guarantee of future returns.</span></div>"
    )


def _reason_html(r):
    why = html.escape("; ".join(r["reasons"]))
    px = r.get("px")
    if px:
        return (f"<span style='color:#2b2820'>{html.escape(_px_label(px))}</span>"
                f"<br><span style='color:#8a8578'>{why}</span>")
    return why


def todays_read(highlights):
    """Plain-English synthesis lines for the top of the email/dashboard.

    Insider BUYING is the informative signal; selling is mostly noise, so the
    read leads with conviction buys and only notes the narrow caution cases."""
    strong = [r for r in highlights if r["signal"] == "STRONG BULLISH"]
    bullish = [r for r in highlights if r["signal"] == "BULLISH"]
    caution = [r for r in highlights if r["signal"] == "CAUTION"]
    conviction = strong + bullish

    def tag(r):
        z = _px_zone(r.get("px"))
        suffix = f" ({z})" if z in ("near 52w low", "near 52w high") else ""
        return f"{r['ticker']}{suffix}"

    lines = []
    if conviction:
        names = ", ".join(dict.fromkeys(tag(r) for r in conviction[:6]))
        lines.append(f"{len(conviction)} conviction buy{'s' if len(conviction) != 1 else ''} today: {names}.")
        # Highest-quality subset: off-schedule ("opportunistic") buyers, the
        # research-backed predictive kind, ideally buying into weakness.
        opp = [r for r in conviction if r.get("timing") == "opportunistic"]
        if opp:
            lines.append("Off-schedule (opportunistic) buyers — historically the predictive kind: "
                         + ", ".join(dict.fromkeys(r["ticker"] for r in opp[:5])) + ".")
        routine = [r for r in conviction if r.get("timing") == "routine"]
        if routine:
            lines.append("Likely scheduled (routine) buyers — carry little signal, discount these: "
                         + ", ".join(dict.fromkeys(r["ticker"] for r in routine[:5])) + ".")
        near_lows = [r for r in conviction if (r.get("px") or {}).get("pos", 1) <= 0.25]
        if near_lows:
            lines.append("Buying into weakness (near 52-week lows): "
                         + ", ".join(dict.fromkeys(r["ticker"] for r in near_lows[:5])) + ".")
    else:
        lines.append("No conviction insider buys today — tape is quiet/neutral.")
    if caution:
        lines.append(f"{len(caution)} caution (large discretionary / cluster sells): "
                     + ", ".join(dict.fromkeys(r["ticker"] for r in caution[:5])) + ".")
    lines.append("Insider buying is the reliable signal here; selling is mostly noise and is de-weighted.")
    return lines

DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Insider Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --parchment: #f4efe6;
    --ink: #2b2820;
    --muted: #8a8578;
    --line: #d8d0bf;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--parchment);
    color: var(--ink);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    padding: 32px 24px 64px;
    max-width: 1100px;
    margin: 0 auto;
  }
  h1, h2 {
    font-family: 'EB Garamond', serif;
    font-weight: 600;
    letter-spacing: 0.01em;
  }
  h1 { font-size: 34px; margin-bottom: 4px; }
  h2 { font-size: 22px; margin: 32px 0 12px; border-bottom: 1px solid var(--line); padding-bottom: 6px; }
  .updated { color: var(--muted); margin-bottom: 24px; }
  table { width: 100%; border-collapse: collapse; }
  th {
    text-align: left; font-weight: 500; color: var(--muted);
    border-bottom: 1px solid var(--line); padding: 8px 10px;
    text-transform: uppercase; font-size: 11px; letter-spacing: 0.06em;
  }
  td { padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  tr:hover td { background: rgba(0,0,0,0.025); }
  .sig {
    display: inline-block; padding: 2px 10px; border-radius: 10px;
    color: #fff; font-size: 11px; font-weight: 500; white-space: nowrap;
  }
  .ticker { font-weight: 500; }
  .reason { color: var(--muted); font-size: 12px; }
  .empty { color: var(--muted); padding: 24px 10px; font-style: italic; }
  .num { text-align: right; }
</style>
</head>
<body>
  <h1>Insider Radar</h1>
  <div class="updated">SEC Form 4 filings &middot; Updated {updated}</div>
  {sections}
</body>
</html>
"""


def _fetch_rows(conn, days=30):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute(
        """SELECT f.accession_number, iss.ticker, iss.name, ins.name,
                  ins.officer_title, ins.is_director, ins.is_ten_percent_owner,
                  f.filed_at, f.form_type, f.is_10b5_1, f.raw_url, f.insider_cik
           FROM filings f
           JOIN issuers iss ON f.issuer_cik = iss.cik
           JOIN insiders ins ON f.insider_cik = ins.cik
           WHERE f.filed_at >= ?
           ORDER BY f.filed_at DESC""",
        (since,),
    )
    rows = []
    for row in cur.fetchall():
        acc = row[0]
        tcur = conn.cursor()
        tcur.execute(
            """SELECT transaction_code, SUM(shares), AVG(price_per_share),
                      SUM(shares * COALESCE(price_per_share, 0))
               FROM transactions WHERE accession_number=? AND is_derivative=0
               GROUP BY transaction_code""",
            (acc,),
        )
        txn_summary = {code: (sh, px, val) for code, sh, px, val in tcur.fetchall()}
        rows.append({
            "accession": acc,
            "ticker": row[1], "issuer": row[2],
            "insider": row[3], "title": row[4],
            "is_director": row[5], "is_ten_pct": row[6],
            "filed_at": row[7], "form_type": row[8], "is_10b5_1": row[9],
            "url": row[10],
            "insider_cik": row[11],
            "txns": txn_summary,
        })
    return rows


def _role(r):
    if r["title"]:
        return r["title"]
    if r["is_director"]:
        return "Director"
    if r["is_ten_pct"]:
        return "10% owner"
    return "Insider"


def _txn_cell(r):
    parts = []
    for code, (sh, px, val) in r["txns"].items():
        label = {"P": "Buy", "S": "Sell", "A": "Award", "M": "Exercise",
                 "G": "Gift", "F": "Tax", "D": "Disposition"}.get(code, code)
        if sh and px:
            parts.append(f"{label} {sh:,.0f} @ ${px:,.2f} (${val:,.0f})")
        elif sh:
            parts.append(f"{label} {sh:,.0f} sh")
        else:
            parts.append(label)
    return "; ".join(parts) if parts else "—"


def _classify_all(conn, cfg, rows):
    from insider_radar import classify_filing
    for r in rows:
        r["signal"], r["reasons"] = classify_filing(conn, cfg, r["accession"])


def _table(rows):
    if not rows:
        return '<div class="empty">No filings in this window.</div>'
    out = ["<table><thead><tr>",
           "<th>Filed</th><th>Ticker</th><th>Insider</th><th>Role</th>",
           "<th>Transaction</th><th>Signal</th><th>Why</th>",
           "</tr></thead><tbody>"]
    for r in rows:
        color = SIGNAL_COLORS.get(r["signal"], "#8a8578")
        flag = " *10b5-1" if r["is_10b5_1"] else ""
        out.append(
            f"<tr><td>{html.escape(r['filed_at'])}</td>"
            f"<td class='ticker'>{html.escape(r['ticker'] or '?')}</td>"
            f"<td>{html.escape(r['insider'] or '?')}</td>"
            f"<td>{html.escape(_role(r))}</td>"
            f"<td>{html.escape(_txn_cell(r))}{flag}</td>"
            f"<td><span class='sig' style='background:{color}'>{r['signal']}</span></td>"
            f"<td class='reason'>{_reason_html(r)}</td></tr>"
        )
    out.append("</tbody></table>")
    return "".join(out)


def _offering_line(o):
    price = f"${o['price']:,.2f}" if o["price"] is not None else "the offering price"
    tk = o["ticker"] or o["name"] or "?"
    return (f"{tk}: {o['insiders']} insiders participated in the offering/conversion "
            f"subscription at {price} on {o['tx_date']}. Not scored as a signal.")


def build_dashboard_and_email(conn, cfg):
    rows = _fetch_rows(conn, days=30)
    _classify_all(conn, cfg, rows)

    # Offering/conversion participations are excluded from the bullish signal
    # sections and shown collapsed, one summary line per issuer.
    from insider_radar import offering_summary
    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    offerings = offering_summary(conn, since)

    order = {"STRONG BULLISH": 0, "BULLISH": 1, "CAUTION": 2, "NEUTRAL": 3}
    excluded = ("NEUTRAL", "OFFERING PARTICIPATION")
    highlights = sorted(
        [r for r in rows if r["signal"] not in excluded],
        key=lambda r: (order.get(r["signal"], 4), r["filed_at"]),
    )

    # Price context for the highlighted names only (one cheap batch call).
    pxmap = fetch_price_context({r["ticker"] for r in highlights})
    for r in highlights:
        r["px"] = pxmap.get(r["ticker"])

    # Record/grade signals vs SPY and classify insider timing (opportunistic
    # vs routine). Best-effort — never let analytics break the daily email.
    scorecard = {}
    try:
        import insider_performance
        perf = insider_performance.update_and_score(conn, cfg, highlights)
        scorecard = perf["scorecard"]
        for r in highlights:
            r["timing"] = perf["timing"].get(r["accession"])
    except Exception as e:
        print(f"  performance/scorecard skipped: {e}")

    read_lines = todays_read(highlights)
    read_html = (
        "<div style='background:#efe7d6;border:1px solid #d8d0bf;border-radius:8px;"
        "padding:14px 16px;margin-bottom:20px'>"
        "<div style='font-family:\"EB Garamond\",serif;font-size:20px;margin-bottom:6px'>Today's read</div>"
        + "".join(f"<div style='margin:2px 0'>{html.escape(l)}</div>" for l in read_lines)
        + "</div>"
    )

    updated = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    offering_html = ""
    if offerings:
        items = "".join(f"<li>{html.escape(_offering_line(o))}</li>" for o in offerings)
        offering_html = (
            f"<h2>Offering / conversion participation ({len(offerings)})</h2>"
            f"<p class='reason' style='margin-bottom:8px'>Fixed-price subscription "
            f"allocations from mutual-to-stock conversions and new-issue offerings. "
            f"Not open-market conviction buys — excluded from bullish signals.</p>"
            f"<ul style='margin-left:18px'>{items}</ul>"
        )

    sections = (
        read_html
        + scorecard_html(scorecard)
        + "<h2>Signals</h2>" + _table(highlights)
        + offering_html
        + "<h2>All filings (30 days)</h2>" + _table(rows)
    )
    DOCS.mkdir(exist_ok=True)
    (DOCS / "insider_radar.html").write_text(
        DASHBOARD_TEMPLATE.replace("{updated}", updated).replace("{sections}", sections),
        encoding="utf-8",
    )

    # Email: inline styles only, highlights + count summary
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    subject = f"Insider Radar - Morning Open - {today}"
    counts = {}
    for r in rows:
        counts[r["signal"]] = counts.get(r["signal"], 0) + 1
    summary_line = " | ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda kv: order.get(kv[0], 4)))

    email_rows = []
    for r in highlights[:25]:
        color = SIGNAL_COLORS.get(r["signal"], "#8a8578")
        email_rows.append(
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>{html.escape(r['filed_at'])}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf;font-weight:bold'>{html.escape(r['ticker'] or '?')}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>{html.escape(r['insider'] or '?')} ({html.escape(_role(r))})</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>{html.escape(_txn_cell(r))}"
            + (f"<br><span style='color:#8a8578;font-size:11px'>{html.escape(_px_label(r.get('px')))}</span>"
               if r.get("px") else "")
            + f"</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>"
            f"<span style='background:{color};color:#fff;padding:2px 8px;border-radius:8px;font-size:11px'>{r['signal']}</span></td>"
            f"</tr>"
        )
    read_email = (
        "<div style='background:#efe7d6;border:1px solid #d8d0bf;border-radius:8px;padding:12px 14px;margin:0 0 16px'>"
        "<div style='font-family:Georgia,serif;font-size:18px;margin-bottom:4px'>Today's read</div>"
        + "".join(f"<div style='margin:2px 0;font-size:13px'>{html.escape(l)}</div>" for l in read_lines)
        + "</div>"
    )
    email_body = (
        f"<div style='font-family:monospace;background:#f4efe6;color:#2b2820;padding:24px'>"
        f"<h1 style='font-family:Georgia,serif;font-size:26px;margin:0 0 4px'>Insider Radar</h1>"
        f"<p style='color:#8a8578;margin:0 0 16px'>{summary_line or 'No filings in window'}</p>"
        + read_email
        + scorecard_html(scorecard)
        + f"<table style='border-collapse:collapse;width:100%;font-size:13px'>"
        f"<tr><th style='text-align:left;padding:6px 10px;color:#8a8578'>Filed</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Ticker</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Insider</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Transaction</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Signal</th></tr>"
        + "".join(email_rows)
        + (f"</table>" if email_rows else "</table><p style='color:#8a8578'>No non-neutral signals today.</p>")
        + (
            "<h2 style='font-family:Georgia,serif;font-size:16px;margin:18px 0 6px'>"
            "Offering / conversion participation</h2>"
            "<ul style='margin:0 0 0 18px;color:#6a6a8a;font-size:12px'>"
            + "".join(f"<li>{html.escape(_offering_line(o))}</li>" for o in offerings[:15])
            + "</ul>"
            if offerings else ""
        )
        + f"<p style='margin-top:16px'><a href='https://gtmautomationops-dev.github.io/market-scanner/insider_radar.html'>Full dashboard</a></p>"
        f"</div>"
    )
    (DOCS / "insider_email.html").write_text(email_body, encoding="utf-8")
    (DOCS / "insider_email_subject.txt").write_text(subject, encoding="utf-8")
    print(f"Dashboard written to docs/insider_radar.html")
    print(f"Email written to docs/insider_email.html — subject: {subject}")
