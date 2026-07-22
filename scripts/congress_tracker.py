"""Congressional Trades Tracker.

Pipeline: House Clerk annual PTR index -> per-filing PDF -> parsed trades ->
committee-jurisdiction overlay -> signals -> SQLite -> dashboard/email.

All inputs are public STOCK Act disclosures. A COMMITTEE CONFLICT flag marks a
lawful, disclosed trade in a sector the member's committee oversees — a
potential conflict of interest to scrutinize, not proof of wrongdoing.
"""

import io
import json
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pdfplumber
import requests
import yaml

from congress_data import CongressRoster
from congress_ptr_parser import parse_ptr_text

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "congress_tracker.yml"
DB_PATH = ROOT / "data" / "congress_trades.db"
RUNLOG_PATH = ROOT / "data" / "congress_runlog.json"

HOUSE_INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
HOUSE_PTR_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"


def load_config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


class HouseClient:
    def __init__(self, cfg):
        s = cfg["scraper"]
        self.session = requests.Session()
        self.session.headers["User-Agent"] = s["user_agent"]
        self.min_interval = 1.0 / s["max_requests_per_second"]
        self.max_retries = s["max_retries"]
        self.backoff = s["backoff_base_seconds"]
        self._last = 0.0

    def get(self, url):
        for attempt in range(self.max_retries):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            resp = self.session.get(url, timeout=60)
            if resp.status_code in (429, 503):
                time.sleep(self.backoff * (2 ** attempt))
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError(f"Gave up after {self.max_retries} retries: {url}")


# ---------------------------------------------------------------- database

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    bioguide TEXT PRIMARY KEY,
    full_name TEXT, party TEXT, chamber TEXT, state TEXT, district INTEGER,
    critical_committees TEXT, committees TEXT
);
CREATE TABLE IF NOT EXISTS filings (
    doc_id TEXT PRIMARY KEY,
    bioguide TEXT, member_name TEXT, state_district TEXT,
    filing_date TEXT, pdf_url TEXT, tx_count INTEGER
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT, bioguide TEXT, member_name TEXT, party TEXT, chamber TEXT,
    ticker TEXT, asset TEXT, tx_type TEXT, tx_type_label TEXT, partial INTEGER,
    tx_date TEXT, notification_date TEXT, filing_date TEXT,
    amount_low INTEGER, amount_high INTEGER,
    conflicts TEXT, signal TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_doc ON trades(doc_id);
CREATE INDEX IF NOT EXISTS idx_trades_signal ON trades(signal, filing_date);
"""


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- index

def _parse_index_date(s):
    for fmt in ("%m/%d/%Y", "%-m/%-d/%Y"):
        try:
            return datetime.strptime(s.strip(), "%m/%d/%Y").date()
        except ValueError:
            pass
    return None


def fetch_ptr_index(client, year):
    """Download the annual FD zip and return PTR (type P) filings as dicts."""
    resp = client.get(HOUSE_INDEX_URL.format(year=year))
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    txt_name = f"{year}FD.txt"
    raw = zf.read(txt_name).decode("utf-8", errors="replace")
    rows = []
    for line in raw.splitlines()[1:]:  # skip header
        parts = line.split("\t")
        if len(parts) < 9:
            continue
        prefix, last, first, suffix, ftype, statedst, yr, filed, doc_id = parts[:9]
        if ftype.strip() != "P":  # Periodic Transaction Report
            continue
        rows.append({
            "last": last.strip(), "first": first.strip(),
            "state_district": statedst.strip(),
            "state": statedst.strip()[:2] if len(statedst.strip()) >= 2 else None,
            "district": int(statedst.strip()[2:]) if statedst.strip()[2:].isdigit() else None,
            "filing_date": filed.strip(),
            "filing_date_obj": _parse_index_date(filed),
            "doc_id": doc_id.strip(),
        })
    return rows


def fetch_ptr_text(client, year, doc_id):
    resp = client.get(HOUSE_PTR_PDF_URL.format(year=year, doc_id=doc_id))
    text = ""
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"
    return text


# ---------------------------------------------------------------- signals

def classify(conflicts, amount_high, large_usd):
    if conflicts:
        return "COMMITTEE CONFLICT"
    if amount_high >= large_usd:
        return "LARGE DISCLOSED"
    return "DISCLOSED"


# ---------------------------------------------------------------- runner

def run_scrape():
    cfg = load_config()
    client = HouseClient(cfg)
    conn = get_db()
    cur = conn.cursor()

    print("Loading committee/legislator roster...")
    roster = CongressRoster(cfg)

    cur.execute("SELECT COUNT(*) FROM filings")
    first_run = cur.fetchone()[0] == 0
    days = cfg["scraper"]["backfill_days"] if first_run else cfg["scraper"]["incremental_days"]
    since = (datetime.now(timezone.utc).date() - timedelta(days=days))
    large_usd = cfg["signals"]["large_usd"]
    print(f"{'First run backfill' if first_run else 'Incremental'}: PTRs filed since {since}")

    index = []
    for year in cfg["scraper"]["years"]:
        rows = fetch_ptr_index(client, year)
        for r in rows:
            r["year"] = year
        index.extend(rows)
        print(f"  {year}: {len(rows)} PTRs in annual index")

    in_window = [r for r in index if r["filing_date_obj"] and r["filing_date_obj"] >= since]
    print(f"  {len(in_window)} PTRs within window")

    stored_filings = stored_trades = skipped_dupe = unparseable = unmatched = 0
    errors = []
    seen_members = {}

    for r in in_window:
        doc_id = r["doc_id"]
        cur.execute("SELECT 1 FROM filings WHERE doc_id=?", (doc_id,))
        if cur.fetchone():
            skipped_dupe += 1
            continue
        try:
            text = fetch_ptr_text(client, r["year"], doc_id)
            parsed = parse_ptr_text(text)
        except Exception as e:
            errors.append(f"{doc_id} ({r['last']}): {e}")
            continue

        if not parsed["transactions"]:
            unparseable += 1
            # still record the filing so we don't refetch a scanned/empty PTR
            cur.execute(
                "INSERT OR REPLACE INTO filings VALUES (?,?,?,?,?,?,?)",
                (doc_id, None, f"{r['first']} {r['last']}", r["state_district"],
                 r["filing_date"], HOUSE_PTR_PDF_URL.format(year=r["year"], doc_id=doc_id), 0),
            )
            continue

        member = roster.match_member(r["last"], r["state"], r["district"])
        bioguide = member["bioguide"] if member else None
        if not member:
            unmatched += 1

        # upsert member record once
        if bioguide and bioguide not in seen_members:
            critical = roster.is_critical(bioguide)
            committees = sorted({c["name"] for c in roster.committees_for(bioguide)})
            cur.execute(
                "INSERT OR REPLACE INTO members VALUES (?,?,?,?,?,?,?,?)",
                (bioguide, member["full_name"], member["party"], member["chamber"],
                 member["state"], member["district"],
                 json.dumps(critical), json.dumps(committees)),
            )
            seen_members[bioguide] = member

        cur.execute(
            "INSERT OR REPLACE INTO filings VALUES (?,?,?,?,?,?,?)",
            (doc_id, bioguide, parsed["member_name"] or f"{r['first']} {r['last']}",
             r["state_district"], r["filing_date"],
             HOUSE_PTR_PDF_URL.format(year=r["year"], doc_id=doc_id),
             len(parsed["transactions"])),
        )
        stored_filings += 1

        for t in parsed["transactions"]:
            conflicts = roster.conflicts_for_trade(bioguide, t["ticker"]) if bioguide else []
            signal = classify(conflicts, t["amount_high"], large_usd)
            cur.execute(
                """INSERT INTO trades
                   (doc_id, bioguide, member_name, party, chamber, ticker, asset,
                    tx_type, tx_type_label, partial, tx_date, notification_date,
                    filing_date, amount_low, amount_high, conflicts, signal)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc_id, bioguide, parsed["member_name"] or f"{r['first']} {r['last']}",
                 member["party"] if member else None,
                 member["chamber"] if member else "house",
                 t["ticker"], t["asset"], t["tx_type"], t["tx_type_label"],
                 int(t["partial"]), t["tx_date"], t["notification_date"],
                 r["filing_date"], t["amount_low"], t["amount_high"],
                 json.dumps(conflicts), signal),
            )
            stored_trades += 1
        conn.commit()

    runlog = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "first_run": first_run,
        "since": str(since),
        "ptrs_in_window": len(in_window),
        "filings_stored": stored_filings,
        "trades_stored": stored_trades,
        "skipped_duplicate": skipped_dupe,
        "unparseable_pdfs": unparseable,
        "unmatched_members": unmatched,
        "errors": errors,
    }
    RUNLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNLOG_PATH.write_text(json.dumps(runlog, indent=2), encoding="utf-8")

    print(f"\n=== Congress Tracker summary ===")
    print(f"  PTRs in window:     {len(in_window)}")
    print(f"  Filings stored:     {stored_filings}")
    print(f"  Trades stored:      {stored_trades}")
    print(f"  Skipped duplicate:  {skipped_dupe}")
    print(f"  Unparseable PDFs:   {unparseable}")
    print(f"  Unmatched members:  {unmatched}")
    print(f"  Errors:             {len(errors)}")
    for e in errors[:15]:
        print(f"    {e}")
    return conn


if __name__ == "__main__":
    if "--dashboard-only" in sys.argv:
        from congress_dashboard import build_dashboard_and_email
        build_dashboard_and_email(get_db(), load_config())
    else:
        conn = run_scrape()
        from congress_dashboard import build_dashboard_and_email
        build_dashboard_and_email(conn, load_config())
