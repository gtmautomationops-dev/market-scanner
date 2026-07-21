"""Insider Radar: SEC EDGAR Form 4 scraper and signal engine."""

import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "insider_radar.yml"
DB_PATH = ROOT / "data" / "insider_radar.db"
RUNLOG_PATH = ROOT / "data" / "insider_radar_runlog.json"

SEC_BASE = "https://www.sec.gov"
EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index?q=%22form+4%22"
EDGAR_BROWSE = "https://www.sec.gov/cgi-bin/browse-edgar"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


class RateLimiter:
    def __init__(self, max_per_second):
        self.min_interval = 1.0 / max_per_second
        self.last = 0.0

    def wait(self):
        elapsed = time.monotonic() - self.last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last = time.monotonic()


class SecClient:
    def __init__(self, cfg):
        s = cfg["scraper"]
        self.session = requests.Session()
        self.session.headers["User-Agent"] = s["user_agent"]
        self.limiter = RateLimiter(s["max_requests_per_second"])
        self.max_retries = s["max_retries"]
        self.backoff_base = s["backoff_base_seconds"]

    def get(self, url, **kwargs):
        for attempt in range(self.max_retries):
            self.limiter.wait()
            resp = self.session.get(url, timeout=30, **kwargs)
            if resp.status_code in (429, 503):
                wait = self.backoff_base * (2 ** attempt)
                print(f"  HTTP {resp.status_code} on {url}, backing off {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError(f"Gave up after {self.max_retries} retries: {url}")


# ---------------------------------------------------------------- database

SCHEMA = """
CREATE TABLE IF NOT EXISTS issuers (
    cik TEXT PRIMARY KEY,
    ticker TEXT,
    name TEXT
);
CREATE TABLE IF NOT EXISTS insiders (
    cik TEXT PRIMARY KEY,
    name TEXT,
    is_director INTEGER DEFAULT 0,
    is_officer INTEGER DEFAULT 0,
    is_ten_percent_owner INTEGER DEFAULT 0,
    officer_title TEXT
);
CREATE TABLE IF NOT EXISTS filings (
    accession_number TEXT PRIMARY KEY,
    issuer_cik TEXT NOT NULL,
    insider_cik TEXT NOT NULL,
    form_type TEXT NOT NULL,
    filed_at TEXT NOT NULL,
    period_of_report TEXT,
    is_10b5_1 INTEGER DEFAULT 0,
    amends_accession TEXT,
    raw_url TEXT,
    FOREIGN KEY (issuer_cik) REFERENCES issuers(cik),
    FOREIGN KEY (insider_cik) REFERENCES insiders(cik)
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accession_number TEXT NOT NULL,
    security_title TEXT,
    is_derivative INTEGER DEFAULT 0,
    transaction_date TEXT,
    transaction_code TEXT,
    shares REAL,
    price_per_share REAL,
    acquired_disposed TEXT,
    shares_owned_after REAL,
    ownership_form TEXT,
    FOREIGN KEY (accession_number) REFERENCES filings(accession_number)
);
CREATE INDEX IF NOT EXISTS idx_filings_issuer ON filings(issuer_cik, filed_at);
CREATE INDEX IF NOT EXISTS idx_txn_accession ON transactions(accession_number);
"""


def get_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- ticker→CIK

def load_ticker_cik_map(client):
    resp = client.get(COMPANY_TICKERS_URL)
    data = resp.json()
    mapping = {}
    for entry in data.values():
        mapping[entry["ticker"].upper()] = str(entry["cik_str"]).zfill(10)
    return mapping


# ---------------------------------------------------------------- Form 4 parsing

def _text(el, path):
    node = el.find(path)
    return node.text.strip() if node is not None and node.text else None


def _value(el, path):
    """Form 4 XML wraps most fields in a <value> child."""
    return _text(el, path + "/value") or _text(el, path)


def _num(el, path):
    v = _value(el, path)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_form4_xml(xml_text):
    """Parse a Form 4 (or 4/A) ownershipDocument XML into a dict.

    Returns None if the document is not a Form 4 family filing.
    """
    xml_text = re.sub(r"<\?xml[^?]*\?>", "", xml_text).strip()
    root = ET.fromstring(xml_text)

    form_type = _text(root, "documentType")
    if form_type not in ("4", "4/A"):
        return None

    issuer = root.find("issuer")
    owner = root.find("reportingOwner")
    if issuer is None or owner is None:
        return None

    rel = owner.find("reportingOwnerRelationship")
    result = {
        "form_type": form_type,
        "period_of_report": _text(root, "periodOfReport"),
        "issuer_cik": (_text(issuer, "issuerCik") or "").zfill(10),
        "issuer_name": _text(issuer, "issuerName"),
        "issuer_ticker": (_text(issuer, "issuerTradingSymbol") or "").upper(),
        "insider_cik": (_text(owner, "reportingOwnerId/rptOwnerCik") or "").zfill(10),
        "insider_name": _text(owner, "reportingOwnerId/rptOwnerName"),
        "is_director": 0,
        "is_officer": 0,
        "is_ten_percent_owner": 0,
        "officer_title": None,
        "is_10b5_1": 0,
        "transactions": [],
    }

    if rel is not None:
        result["is_director"] = 1 if _value(rel, "isDirector") in ("1", "true") else 0
        result["is_officer"] = 1 if _value(rel, "isOfficer") in ("1", "true") else 0
        result["is_ten_percent_owner"] = 1 if _value(rel, "isTenPercentOwner") in ("1", "true") else 0
        result["officer_title"] = _value(rel, "officerTitle")

    # Rule 10b5-1(c) flag appears at document level (2023+ schema) or in footnotes
    flag = root.find("aff10b5One")
    if flag is not None and (flag.text or "").strip() in ("1", "true"):
        result["is_10b5_1"] = 1
    else:
        footnotes = root.find("footnotes")
        if footnotes is not None:
            all_notes = " ".join((n.text or "") for n in footnotes)
            if "10b5-1" in all_notes:
                result["is_10b5_1"] = 1

    for table, is_deriv in (("nonDerivativeTable", 0), ("derivativeTable", 1)):
        tbl = root.find(table)
        if tbl is None:
            continue
        tag = "derivativeTransaction" if is_deriv else "nonDerivativeTransaction"
        for txn in tbl.findall(tag):
            amounts = txn.find("transactionAmounts")
            post = txn.find("postTransactionAmounts")
            result["transactions"].append({
                "security_title": _value(txn, "securityTitle"),
                "is_derivative": is_deriv,
                "transaction_date": _value(txn, "transactionDate"),
                "transaction_code": _text(txn, "transactionCoding/transactionCode"),
                "shares": _num(amounts, "transactionShares") if amounts is not None else None,
                "price_per_share": _num(amounts, "transactionPricePerShare") if amounts is not None else None,
                "acquired_disposed": _value(amounts, "transactionAcquiredDisposedCode") if amounts is not None else None,
                "shares_owned_after": _num(post, "sharesOwnedFollowingTransaction") if post is not None else None,
                "ownership_form": _value(txn, "ownershipNature/directOrIndirectOwnership"),
            })

    return result


# ---------------------------------------------------------------- scraping

def fetch_recent_form4_index(client, cik, since_date):
    """List Form 4 filings for an issuer CIK since a given date via the
    submissions API. Returns list of (accession_number, filed_at, form_type)."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = client.get(url)
    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})
    out = []
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    docs = recent.get("primaryDocument", [])
    for form, acc, fdate, doc in zip(forms, accessions, dates, docs):
        if form not in ("4", "4/A"):
            continue
        if fdate < since_date:
            continue
        out.append((acc, fdate, form, doc))
    return out


def fetch_form4_document(client, cik, accession, primary_doc):
    acc_nodash = accession.replace("-", "")
    cik_int = str(int(cik))
    url = f"{SEC_BASE}/Archives/edgar/data/{cik_int}/{acc_nodash}/{primary_doc}"
    resp = client.get(url)
    text = resp.text
    # Primary doc may be the XML itself, or an HTML wrapper; find the XML
    if "<ownershipDocument>" not in text:
        # Fetch the raw .txt submission and extract the XML block
        url_txt = f"{SEC_BASE}/Archives/edgar/data/{cik_int}/{acc_nodash}/{accession}.txt"
        resp = client.get(url_txt)
        text = resp.text
    m = re.search(r"<ownershipDocument>.*?</ownershipDocument>", text, re.DOTALL)
    if not m:
        return None, url
    return "<?xml version=\"1.0\"?>" + m.group(0), url


def store_filing(conn, parsed, accession, filed_at, raw_url):
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO issuers (cik, ticker, name) VALUES (?, ?, ?)",
        (parsed["issuer_cik"], parsed["issuer_ticker"], parsed["issuer_name"]),
    )
    cur.execute(
        """INSERT OR REPLACE INTO insiders
           (cik, name, is_director, is_officer, is_ten_percent_owner, officer_title)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (parsed["insider_cik"], parsed["insider_name"], parsed["is_director"],
         parsed["is_officer"], parsed["is_ten_percent_owner"], parsed["officer_title"]),
    )

    amends = None
    if parsed["form_type"] == "4/A":
        # An amendment replaces the original filing for the same issuer,
        # insider, and period. Remove the superseded original.
        cur.execute(
            """SELECT accession_number FROM filings
               WHERE issuer_cik=? AND insider_cik=? AND period_of_report=?
                 AND form_type='4'""",
            (parsed["issuer_cik"], parsed["insider_cik"], parsed["period_of_report"]),
        )
        row = cur.fetchone()
        if row:
            amends = row[0]
            cur.execute("DELETE FROM transactions WHERE accession_number=?", (amends,))
            cur.execute("DELETE FROM filings WHERE accession_number=?", (amends,))

    cur.execute(
        """INSERT OR REPLACE INTO filings
           (accession_number, issuer_cik, insider_cik, form_type, filed_at,
            period_of_report, is_10b5_1, amends_accession, raw_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (accession, parsed["issuer_cik"], parsed["insider_cik"], parsed["form_type"],
         filed_at, parsed["period_of_report"], parsed["is_10b5_1"], amends, raw_url),
    )
    cur.execute("DELETE FROM transactions WHERE accession_number=?", (accession,))
    for t in parsed["transactions"]:
        cur.execute(
            """INSERT INTO transactions
               (accession_number, security_title, is_derivative, transaction_date,
                transaction_code, shares, price_per_share, acquired_disposed,
                shares_owned_after, ownership_form)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (accession, t["security_title"], t["is_derivative"], t["transaction_date"],
             t["transaction_code"], t["shares"], t["price_per_share"],
             t["acquired_disposed"], t["shares_owned_after"], t["ownership_form"]),
        )
    conn.commit()


# ---------------------------------------------------------------- signals

def is_ceo_cfo(officer_title):
    if not officer_title:
        return False
    t = officer_title.lower()
    return any(k in t for k in ("chief executive", "chief financial", "ceo", "cfo"))


def classify_filing(conn, cfg, accession):
    """Classify one filing. Returns (signal, reasons)."""
    sig_cfg = cfg["signals"]
    cur = conn.cursor()
    cur.execute(
        """SELECT f.issuer_cik, f.insider_cik, f.is_10b5_1, f.filed_at,
                  i.officer_title, i.is_officer
           FROM filings f JOIN insiders i ON f.insider_cik = i.cik
           WHERE f.accession_number=?""",
        (accession,),
    )
    row = cur.fetchone()
    if not row:
        return "NEUTRAL", ["filing not found"]
    issuer_cik, insider_cik, is_10b5_1, filed_at, officer_title, is_officer = row

    cur.execute(
        """SELECT transaction_code, shares, price_per_share, acquired_disposed,
                  shares_owned_after, is_derivative
           FROM transactions WHERE accession_number=?""",
        (accession,),
    )
    txns = cur.fetchall()

    buy_value = sell_value = 0.0
    pre_buy_owned = post_owned = None
    for code, shares, price, ad, owned_after, is_deriv in txns:
        value = (shares or 0) * (price or 0)
        if code == "P":
            buy_value += value
            if owned_after is not None:
                post_owned = owned_after
                if shares:
                    pre_buy_owned = owned_after - shares
        elif code == "S":
            sell_value += value
            if owned_after is not None:
                post_owned = owned_after
                if shares:
                    pre_buy_owned = owned_after + shares

    reasons = []
    ceo_cfo = bool(is_officer) and is_ceo_cfo(officer_title)

    # Stake change fraction
    stake_change = None
    if pre_buy_owned and pre_buy_owned > 0 and post_owned is not None:
        stake_change = (post_owned - pre_buy_owned) / pre_buy_owned

    # --- CAUTION checks
    if ceo_cfo and not is_10b5_1 and sell_value > sig_cfg["officer_caution_sell_usd"]:
        reasons.append(f"CEO/CFO non-10b5-1 sell ${sell_value:,.0f}")
        return "CAUTION", reasons
    if stake_change is not None and stake_change < -sig_cfg["stake_reduction_caution"]:
        reasons.append(f"stake reduced {abs(stake_change):.0%}")
        return "CAUTION", reasons

    # Cluster detection (buys and sells)
    window_start = (
        datetime.strptime(filed_at, "%Y-%m-%d")
        - timedelta(days=sig_cfg["cluster_window_days"])
    ).strftime("%Y-%m-%d")
    cur.execute(
        """SELECT COUNT(DISTINCT f.insider_cik)
           FROM filings f JOIN transactions t ON f.accession_number = t.accession_number
           WHERE f.issuer_cik=? AND t.transaction_code='P'
             AND f.filed_at BETWEEN ? AND ?""",
        (issuer_cik, window_start, filed_at),
    )
    cluster_buyers = cur.fetchone()[0]
    cur.execute(
        """SELECT COUNT(DISTINCT f.insider_cik)
           FROM filings f JOIN transactions t ON f.accession_number = t.accession_number
           WHERE f.issuer_cik=? AND t.transaction_code='S'
             AND f.filed_at BETWEEN ? AND ?""",
        (issuer_cik, window_start, filed_at),
    )
    cluster_sellers = cur.fetchone()[0]

    if buy_value == 0 and sell_value > 0 and cluster_sellers >= sig_cfg["cluster_min_insiders"]:
        reasons.append(f"cluster sell: {cluster_sellers} insiders in {sig_cfg['cluster_window_days']}d")
        return "CAUTION", reasons

    # --- STRONG BULLISH checks
    if buy_value > 0 and cluster_buyers >= sig_cfg["cluster_min_insiders"]:
        reasons.append(f"cluster buy: {cluster_buyers} insiders in {sig_cfg['cluster_window_days']}d")
        return "STRONG BULLISH", reasons
    if ceo_cfo and not is_10b5_1 and buy_value > sig_cfg["officer_strong_buy_usd"]:
        reasons.append(f"CEO/CFO non-10b5-1 buy ${buy_value:,.0f}")
        return "STRONG BULLISH", reasons

    # --- BULLISH checks
    if buy_value > sig_cfg["notable_buy_usd"]:
        reasons.append(f"notable buy ${buy_value:,.0f}")
        return "BULLISH", reasons
    if ceo_cfo and buy_value > 0:
        reasons.append(f"CEO/CFO buy ${buy_value:,.0f}")
        return "BULLISH", reasons
    if stake_change is not None and stake_change > sig_cfg["stake_increase_bullish"]:
        reasons.append(f"stake increased {stake_change:.0%}")
        return "BULLISH", reasons

    # --- NEUTRAL
    if is_10b5_1:
        reasons.append("10b5-1 planned trade")
    elif sell_value > 0:
        reasons.append(f"sell ${sell_value:,.0f} below caution threshold")
    elif buy_value > 0:
        reasons.append(f"small buy ${buy_value:,.0f}")
    else:
        reasons.append("routine (exercise/award/gift)")
    return "NEUTRAL", reasons


# ---------------------------------------------------------------- runner

def run_scrape():
    cfg = load_config()
    client = SecClient(cfg)
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM filings")
    first_run = cur.fetchone()[0] == 0
    backfill_days = cfg["scraper"]["backfill_days"] if first_run else 3
    since = (datetime.now(timezone.utc) - timedelta(days=backfill_days)).strftime("%Y-%m-%d")
    print(f"{'First run: backfilling' if first_run else 'Incremental scrape since'} {since}")

    print("Loading SEC ticker->CIK map...")
    cik_map = load_ticker_cik_map(client)

    watchlist = cfg["watchlist"]
    unresolved = [t for t in watchlist if t.upper() not in cik_map]
    resolved = [(t, cik_map[t.upper()]) for t in watchlist if t.upper() in cik_map]
    print(f"Watchlist: {len(watchlist)} tickers, {len(resolved)} resolved to CIK, {len(unresolved)} unresolved")
    if unresolved:
        print(f"  Unresolved (no SEC CIK — foreign issuer or unlisted): {', '.join(unresolved)}")

    new_filings = 0
    errors = []
    for ticker, cik in resolved:
        try:
            filings = fetch_recent_form4_index(client, cik, since)
        except Exception as e:
            errors.append((ticker, f"index fetch: {e}"))
            continue
        for accession, filed_at, form_type, primary_doc in filings:
            cur.execute("SELECT 1 FROM filings WHERE accession_number=?", (accession,))
            if cur.fetchone() and form_type != "4/A":
                continue
            try:
                xml_text, raw_url = fetch_form4_document(client, cik, accession, primary_doc)
                if xml_text is None:
                    errors.append((ticker, f"{accession}: no ownershipDocument found"))
                    continue
                parsed = parse_form4_xml(xml_text)
                if parsed is None:
                    continue
                store_filing(conn, parsed, accession, filed_at, raw_url)
                new_filings += 1
            except Exception as e:
                errors.append((ticker, f"{accession}: {e}"))
        print(f"  {ticker}: {len(filings)} filings in window")

    # Classify everything in the recent window
    cur.execute(
        "SELECT accession_number FROM filings WHERE filed_at >= ?", (since,)
    )
    classified = []
    for (accession,) in cur.fetchall():
        signal, reasons = classify_filing(conn, cfg, accession)
        classified.append({"accession": accession, "signal": signal, "reasons": reasons})

    runlog = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "first_run": first_run,
        "since": since,
        "watchlist_size": len(watchlist),
        "resolved": len(resolved),
        "unresolved": unresolved,
        "new_filings": new_filings,
        "classified": classified,
        "errors": [f"{t}: {msg}" for t, msg in errors],
    }
    RUNLOG_PATH.parent.mkdir(exist_ok=True)
    RUNLOG_PATH.write_text(json.dumps(runlog, indent=2), encoding="utf-8")

    print(f"\n=== Insider Radar scrape summary ===")
    print(f"  New filings stored: {new_filings}")
    print(f"  Errors: {len(errors)}")
    for t, msg in errors[:20]:
        print(f"    {t}: {msg}")
    print(f"  Runlog written to {RUNLOG_PATH}")
    return conn


if __name__ == "__main__":
    if "--dashboard-only" in sys.argv:
        from insider_dashboard import build_dashboard_and_email
        build_dashboard_and_email(get_db(), load_config())
    else:
        conn = run_scrape()
        from insider_dashboard import build_dashboard_and_email
        build_dashboard_and_email(conn, load_config())
