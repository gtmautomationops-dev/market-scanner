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
}

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
                  f.filed_at, f.form_type, f.is_10b5_1, f.raw_url
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
            f"<td class='reason'>{html.escape('; '.join(r['reasons']))}</td></tr>"
        )
    out.append("</tbody></table>")
    return "".join(out)


def build_dashboard_and_email(conn, cfg):
    rows = _fetch_rows(conn, days=30)
    _classify_all(conn, cfg, rows)

    order = {"STRONG BULLISH": 0, "BULLISH": 1, "CAUTION": 2, "NEUTRAL": 3}
    highlights = sorted(
        [r for r in rows if r["signal"] != "NEUTRAL"],
        key=lambda r: (order.get(r["signal"], 4), r["filed_at"]),
    )

    updated = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    sections = (
        "<h2>Signals</h2>" + _table(highlights)
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
            f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>{html.escape(_txn_cell(r))}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>"
            f"<span style='background:{color};color:#fff;padding:2px 8px;border-radius:8px;font-size:11px'>{r['signal']}</span></td>"
            f"</tr>"
        )
    email_body = (
        f"<div style='font-family:monospace;background:#f4efe6;color:#2b2820;padding:24px'>"
        f"<h1 style='font-family:Georgia,serif;font-size:26px;margin:0 0 4px'>Insider Radar</h1>"
        f"<p style='color:#8a8578;margin:0 0 16px'>{summary_line or 'No filings in window'}</p>"
        f"<table style='border-collapse:collapse;width:100%;font-size:13px'>"
        f"<tr><th style='text-align:left;padding:6px 10px;color:#8a8578'>Filed</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Ticker</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Insider</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Transaction</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Signal</th></tr>"
        + "".join(email_rows)
        + (f"</table>" if email_rows else "</table><p style='color:#8a8578'>No non-neutral signals today.</p>")
        + f"<p style='margin-top:16px'><a href='https://gtmautomationops-dev.github.io/market-scanner/insider_radar.html'>Full dashboard</a></p>"
        f"</div>"
    )
    (DOCS / "insider_email.html").write_text(email_body, encoding="utf-8")
    (DOCS / "insider_email_subject.txt").write_text(subject, encoding="utf-8")
    print(f"Dashboard written to docs/insider_radar.html")
    print(f"Email written to docs/insider_email.html — subject: {subject}")
