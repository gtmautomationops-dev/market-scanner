"""Congressional Trades Tracker: dashboard + email generation."""

import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

SIGNAL_COLORS = {
    "COMMITTEE CONFLICT": "#b0413e",
    "LARGE DISCLOSED": "#8a6d1f",
    "DISCLOSED": "#8a8578",
}
SIGNAL_ORDER = {"COMMITTEE CONFLICT": 0, "LARGE DISCLOSED": 1, "DISCLOSED": 2}
PARTY_COLOR = {"Democrat": "#2b5d9e", "Republican": "#b0413e", "Independent": "#6a6a6a"}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Congress Trades Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{--parchment:#f4efe6;--ink:#2b2820;--muted:#8a8578;--line:#d8d0bf;}
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:var(--parchment);color:var(--ink);font-family:'IBM Plex Mono',monospace;
       font-size:13px;padding:32px 24px 64px;max-width:1150px;margin:0 auto;}
  h1,h2{font-family:'EB Garamond',serif;font-weight:600;}
  h1{font-size:34px;margin-bottom:4px;}
  h2{font-size:22px;margin:34px 0 12px;border-bottom:1px solid var(--line);padding-bottom:6px;}
  .sub{color:var(--muted);margin-bottom:8px;}
  .note{color:var(--muted);font-size:12px;margin-bottom:20px;max-width:760px;line-height:1.5;}
  table{width:100%;border-collapse:collapse;}
  th{text-align:left;font-weight:500;color:var(--muted);border-bottom:1px solid var(--line);
     padding:8px 10px;text-transform:uppercase;font-size:11px;letter-spacing:.06em;}
  td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;}
  tr:hover td{background:rgba(0,0,0,.025);}
  .sig{display:inline-block;padding:2px 9px;border-radius:10px;color:#fff;font-size:10px;
       font-weight:500;white-space:nowrap;}
  .party{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;}
  .buy{color:#1a7a3a;font-weight:500;}
  .sell{color:#b0413e;font-weight:500;}
  .why{color:var(--muted);font-size:12px;}
  .badge{display:inline-block;background:#e8e0cf;color:#5a5340;border-radius:4px;
         padding:1px 6px;font-size:10px;margin:1px 2px 1px 0;}
  .empty{color:var(--muted);font-style:italic;padding:20px 10px;}
  .tkr{font-weight:500;}
</style>
</head>
<body>
  <h1>Congress Trades Tracker</h1>
  <div class="sub">House STOCK Act disclosures &middot; Updated {updated}</div>
  <div class="note">Every trade below is a lawfully filed public disclosure. A
  <strong>Committee Conflict</strong> flag means the member sits on a committee with
  jurisdiction over the sector they traded — a potential conflict of interest worth
  scrutiny, not evidence of wrongdoing. Amounts are disclosed as ranges, and filings
  can lag the trade by up to 45 days.</div>
  {sections}
</body>
</html>
"""


def _fetch(conn, days_limit=400):
    cur = conn.cursor()
    cur.execute(
        """SELECT t.member_name, t.party, t.chamber, t.ticker, t.asset,
                  t.tx_type_label, t.partial, t.tx_date, t.filing_date,
                  t.amount_low, t.amount_high, t.conflicts, t.signal,
                  m.critical_committees, m.state, m.district
           FROM trades t LEFT JOIN members m ON t.bioguide = m.bioguide
           WHERE t.ticker IS NOT NULL
           ORDER BY t.filing_date DESC"""
    )
    rows = []
    for r in cur.fetchall():
        conflicts = json.loads(r[11] or "[]")
        critical = json.loads(r[13] or "[]")
        rows.append({
            "member": r[0], "party": r[1], "chamber": r[2],
            "ticker": r[3], "asset": r[4], "action": r[5], "partial": r[6],
            "tx_date": r[7], "filing_date": r[8],
            "amount_low": r[9], "amount_high": r[10],
            "conflicts": conflicts, "signal": r[12], "critical": critical,
            "state": r[14], "district": r[15],
        })
    return rows


def _amount(r):
    return f"${r['amount_low']:,} – ${r['amount_high']:,}"


def _action_cell(r):
    cls = "buy" if r["action"] == "Purchase" else ("sell" if r["action"] == "Sale" else "")
    label = r["action"] + (" (partial)" if r["partial"] else "")
    return f"<span class='{cls}'>{html.escape(label)}</span>"


def _member_cell(r):
    color = PARTY_COLOR.get(r["party"], "#6a6a6a")
    loc = ""
    if r["state"]:
        loc = f" ({r['state']}{('-' + str(r['district'])) if r['district'] else ''})"
    dot = f"<span class='party' style='background:{color}'></span>"
    badges = "".join(
        f"<span class='badge'>{html.escape(c.replace('House Committee on ','').replace('Senate Committee on ',''))}</span>"
        for c in r["critical"]
    )
    return f"{dot}{html.escape(r['member'] or '?')}{html.escape(loc)}<br>{badges}"


def _why_cell(r):
    if r["conflicts"]:
        parts = sorted({f"{c['committee'].replace('House Committee on ','').replace('Senate Committee on ','')} → {c['sector']}"
                        for c in r["conflicts"]})
        return "; ".join(html.escape(p) for p in parts)
    if r["signal"] == "LARGE DISCLOSED":
        return "large disclosed trade"
    return ""


def _table(rows):
    if not rows:
        return '<div class="empty">No trades in this view.</div>'
    out = ["<table><thead><tr>",
           "<th>Filed</th><th>Member</th><th>Ticker</th><th>Action</th>",
           "<th>Amount</th><th>Flag</th><th>Why</th></tr></thead><tbody>"]
    for r in rows:
        color = SIGNAL_COLORS.get(r["signal"], "#8a8578")
        short = {"COMMITTEE CONFLICT": "CONFLICT", "LARGE DISCLOSED": "LARGE",
                 "DISCLOSED": "DISCLOSED"}.get(r["signal"], r["signal"])
        out.append(
            f"<tr><td>{html.escape(r['filing_date'])}</td>"
            f"<td>{_member_cell(r)}</td>"
            f"<td class='tkr'>{html.escape(r['ticker'])}</td>"
            f"<td>{_action_cell(r)}</td>"
            f"<td>{html.escape(_amount(r))}</td>"
            f"<td><span class='sig' style='background:{color}'>{short}</span></td>"
            f"<td class='why'>{_why_cell(r)}</td></tr>"
        )
    out.append("</tbody></table>")
    return "".join(out)


def build_dashboard_and_email(conn, cfg):
    rows = _fetch(conn)
    rows.sort(key=lambda r: (SIGNAL_ORDER.get(r["signal"], 3), r["filing_date"]), reverse=False)

    conflicts = [r for r in rows if r["signal"] == "COMMITTEE CONFLICT"]
    large = [r for r in rows if r["signal"] == "LARGE DISCLOSED"]

    updated = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    sections = (
        f"<h2>⚠ Committee-jurisdiction conflicts ({len(conflicts)})</h2>" + _table(conflicts)
        + f"<h2>Large disclosed trades ({len(large)})</h2>" + _table(large[:60])
        + f"<h2>All recent trades ({len(rows)})</h2>" + _table(rows[:250])
    )
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "congress_tracker.html").write_text(
        PAGE.replace("{updated}", updated).replace("{sections}", sections), encoding="utf-8"
    )

    # ---- email ----
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    subject = f"Congress Trades — {len(conflicts)} committee conflicts — {today}"

    def email_rows(rs):
        out = []
        for r in rs[:30]:
            color = SIGNAL_COLORS.get(r["signal"], "#8a8578")
            why = _why_cell(r)
            out.append(
                f"<tr>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>{html.escape(r['filing_date'])}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>{html.escape(r['member'] or '?')} ({html.escape(r['party'] or '?')})</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf;font-weight:bold'>{html.escape(r['ticker'])}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>{html.escape(r['action'])}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>{html.escape(_amount(r))}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #d8d0bf'>{html.escape(why)}</td></tr>"
            )
        return "".join(out)

    body = (
        f"<div style='font-family:monospace;background:#f4efe6;color:#2b2820;padding:24px'>"
        f"<h1 style='font-family:Georgia,serif;font-size:26px;margin:0 0 4px'>Congress Trades Tracker</h1>"
        f"<p style='color:#8a8578;margin:0 0 16px'>House STOCK Act disclosures · "
        f"{len(conflicts)} committee-jurisdiction conflicts, {len(large)} large trades</p>"
        f"<h2 style='font-family:Georgia,serif;font-size:18px;color:#b0413e'>⚠ Committee-jurisdiction conflicts</h2>"
        f"<table style='border-collapse:collapse;width:100%;font-size:13px'>"
        f"<tr><th style='text-align:left;padding:6px 10px;color:#8a8578'>Filed</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Member</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Ticker</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Action</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Amount</th>"
        f"<th style='text-align:left;padding:6px 10px;color:#8a8578'>Committee → sector</th></tr>"
        + (email_rows(conflicts) if conflicts else
           "<tr><td colspan=6 style='padding:10px;color:#8a8578'>None in this window.</td></tr>")
        + "</table>"
        f"<p style='color:#8a8578;font-size:12px;margin-top:8px'>Disclosed public filings; a flag is a "
        f"potential conflict of interest, not proof of wrongdoing.</p>"
        f"<p style='margin-top:16px'><a href='https://gtmautomationops-dev.github.io/market-scanner/congress_tracker.html'>Full dashboard</a></p>"
        f"</div>"
    )
    (DOCS / "congress_email.html").write_text(body, encoding="utf-8")
    (DOCS / "congress_email_subject.txt").write_text(subject, encoding="utf-8")
    print(f"Dashboard: docs/congress_tracker.html")
    print(f"Email: docs/congress_email.html — subject: {subject}")
