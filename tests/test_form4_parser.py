"""Tests for Form 4 parsing and signal classification.

Fixtures are modeled on real EDGAR ownershipDocument XML structure
(schema version X0407/X0508 as filed).
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import insider_radar
from insider_radar import (
    parse_form4_xml, classify_filing, store_filing, SCHEMA,
    mark_offering_purchases,
)

FIXTURES = Path(__file__).parent / "fixtures"

CFG = {
    "signals": {
        "cluster_window_days": 30,
        "cluster_min_insiders": 3,
        "notable_buy_usd": 250000,
        "officer_strong_buy_usd": 500000,
        "officer_caution_sell_usd": 1000000,
        "routine_sell_usd": 1000000,
        "stake_increase_bullish": 0.20,
        "stake_reduction_caution": 0.50,
        "offering_min_insiders": 3,
        # condition-2 new-issue check is exercised in its own test with an
        # injected stub; keep it off by default so tests stay offline.
        "check_new_issue": False,
        "new_issue_trading_days": 10,
    }
}


def _buy_filing(insider_cik, insider_name, price, date, officer=False,
                title=None, issuer="0000900001", ticker="CLBK"):
    """Build a parsed Form 4 dict for one insider's code-P purchase."""
    return {
        "form_type": "4", "period_of_report": date,
        "issuer_cik": issuer, "issuer_name": "Columbia Financial",
        "issuer_ticker": ticker,
        "insider_cik": insider_cik, "insider_name": insider_name,
        "is_director": 0, "is_officer": int(officer),
        "is_ten_percent_owner": 0, "officer_title": title, "is_10b5_1": 0,
        "transactions": [{
            "security_title": "Common Stock", "is_derivative": 0,
            "transaction_date": date, "transaction_code": "P",
            "shares": 50000, "price_per_share": price,
            "acquired_disposed": "A", "shares_owned_after": 50000,
            "ownership_form": "D",
        }],
    }


def load_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- parsing

def test_parse_ceo_open_market_purchase():
    parsed = parse_form4_xml(load_fixture("form4_ceo_purchase.xml"))
    assert parsed is not None
    assert parsed["form_type"] == "4"
    assert parsed["issuer_ticker"] == "ACME"
    assert parsed["issuer_cik"] == "0000320193"
    assert parsed["insider_name"] == "DOE JANE"
    assert parsed["is_officer"] == 1
    assert parsed["officer_title"] == "Chief Executive Officer"
    assert parsed["is_10b5_1"] == 0
    assert len(parsed["transactions"]) == 1
    txn = parsed["transactions"][0]
    assert txn["transaction_code"] == "P"
    assert txn["shares"] == 50000
    assert txn["price_per_share"] == 14.50
    assert txn["acquired_disposed"] == "A"
    assert txn["shares_owned_after"] == 250000
    assert txn["is_derivative"] == 0


def test_parse_10b5_1_sale():
    parsed = parse_form4_xml(load_fixture("form4_10b5_1_sale.xml"))
    assert parsed is not None
    assert parsed["is_10b5_1"] == 1
    txn = parsed["transactions"][0]
    assert txn["transaction_code"] == "S"
    assert txn["acquired_disposed"] == "D"


def test_parse_derivative_table():
    parsed = parse_form4_xml(load_fixture("form4_derivative_exercise.xml"))
    assert parsed is not None
    codes = {(t["transaction_code"], t["is_derivative"]) for t in parsed["transactions"]}
    # Option exercise appears in the derivative table, resulting share
    # acquisition and same-day sale in the non-derivative table
    assert ("M", 1) in codes
    assert ("M", 0) in codes
    assert ("S", 0) in codes
    deriv = [t for t in parsed["transactions"] if t["is_derivative"]][0]
    assert deriv["security_title"] == "Stock Option (Right to Buy)"
    assert deriv["shares"] == 20000


def test_parse_director_small_buy():
    parsed = parse_form4_xml(load_fixture("form4_director_buy.xml"))
    assert parsed is not None
    assert parsed["is_director"] == 1
    assert parsed["is_officer"] == 0
    assert parsed["transactions"][0]["transaction_code"] == "P"


def test_parse_rejects_non_form4():
    xml = "<?xml version=\"1.0\"?><ownershipDocument><documentType>3</documentType></ownershipDocument>"
    assert parse_form4_xml(xml) is None


# ---------------------------------------------------------------- storage

def test_store_and_dedupe():
    conn = make_db()
    parsed = parse_form4_xml(load_fixture("form4_ceo_purchase.xml"))
    store_filing(conn, parsed, "0000320193-26-000101", "2026-07-15", "http://example")
    store_filing(conn, parsed, "0000320193-26-000101", "2026-07-15", "http://example")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM filings")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM transactions")
    assert cur.fetchone()[0] == 1


def test_amendment_replaces_original():
    conn = make_db()
    original = parse_form4_xml(load_fixture("form4_ceo_purchase.xml"))
    store_filing(conn, original, "0000320193-26-000101", "2026-07-15", "http://example")
    amended = dict(original)
    amended["form_type"] = "4/A"
    store_filing(conn, amended, "0000320193-26-000150", "2026-07-16", "http://example")
    cur = conn.cursor()
    cur.execute("SELECT accession_number, form_type, amends_accession FROM filings")
    rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "0000320193-26-000150"
    assert rows[0][1] == "4/A"
    assert rows[0][2] == "0000320193-26-000101"


# ---------------------------------------------------------------- signals

def test_ceo_large_purchase_is_strong_bullish():
    conn = make_db()
    parsed = parse_form4_xml(load_fixture("form4_ceo_purchase.xml"))
    store_filing(conn, parsed, "acc-1", "2026-07-15", "u")
    signal, reasons = classify_filing(conn, CFG, "acc-1")
    # 50,000 * $14.50 = $725,000 non-10b5-1 CEO buy > $500K threshold
    assert signal == "STRONG BULLISH", reasons


def test_10b5_1_sale_is_neutral():
    conn = make_db()
    parsed = parse_form4_xml(load_fixture("form4_10b5_1_sale.xml"))
    store_filing(conn, parsed, "acc-2", "2026-07-15", "u")
    signal, reasons = classify_filing(conn, CFG, "acc-2")
    assert signal == "NEUTRAL", reasons


def test_director_small_buy_is_neutral():
    conn = make_db()
    parsed = parse_form4_xml(load_fixture("form4_director_buy.xml"))
    store_filing(conn, parsed, "acc-3", "2026-07-15", "u")
    signal, reasons = classify_filing(conn, CFG, "acc-3")
    # 1,000 * $42 = $42,000 — below the $250K notable-buy threshold
    assert signal == "NEUTRAL", reasons


def test_cluster_buy_is_strong_bullish():
    conn = make_db()
    base = parse_form4_xml(load_fixture("form4_director_buy.xml"))
    for i in range(3):
        p = dict(base)
        p["insider_cik"] = f"000000900{i}"
        p["insider_name"] = f"INSIDER {i}"
        store_filing(conn, p, f"acc-c{i}", "2026-07-15", "u")
    signal, reasons = classify_filing(conn, CFG, "acc-c0")
    assert signal == "STRONG BULLISH", reasons
    assert any("cluster buy" in r for r in reasons)


def test_10b5_1_cluster_sells_stay_neutral():
    """Multiple insiders selling under 10b5-1 plans is routine, not a
    cluster-sell CAUTION — planned trades carry no conviction signal."""
    conn = make_db()
    base = parse_form4_xml(load_fixture("form4_10b5_1_sale.xml"))
    for i in range(4):
        p = dict(base)
        p["insider_cik"] = f"000000800{i}"
        p["insider_name"] = f"SELLER {i}"
        store_filing(conn, p, f"acc-s{i}", "2026-07-15", "u")
    signal, reasons = classify_filing(conn, CFG, "acc-s0")
    assert signal == "NEUTRAL", reasons


def test_exercise_and_sale_below_threshold_is_neutral():
    conn = make_db()
    parsed = parse_form4_xml(load_fixture("form4_derivative_exercise.xml"))
    store_filing(conn, parsed, "acc-4", "2026-07-15", "u")
    signal, reasons = classify_filing(conn, CFG, "acc-4")
    # Routine option exercise + sale under $1M by a non-CEO/CFO officer
    assert signal == "NEUTRAL", reasons


# ---------------------------------------------------------------- offering detection

def _load_clbk_conversion(conn):
    """15-insider-style conversion: several insiders buy code P at $10.00 same day."""
    for i in range(5):
        p = _buy_filing(f"000000110{i}", f"OFFICER {i}", 10.00, "2026-07-21",
                        officer=(i == 0), title="Chief Executive Officer" if i == 0 else None)
        store_filing(conn, p, f"clbk-{i}", "2026-07-21", "u")


def test_conversion_flagged_as_offering_purchase():
    conn = make_db()
    _load_clbk_conversion(conn)
    flagged = mark_offering_purchases(conn, CFG)
    assert flagged == 5, flagged
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM transactions WHERE is_offering_purchase=1")
    assert cur.fetchone()[0] == 5


def test_conversion_not_strong_bullish():
    conn = make_db()
    _load_clbk_conversion(conn)
    mark_offering_purchases(conn, CFG)
    # Even the CEO's $500k+ buy must NOT be bullish — it is a fixed-price
    # subscription allocation, not an open-market conviction buy.
    signal, reasons = classify_filing(conn, CFG, "clbk-0")
    assert signal == "OFFERING PARTICIPATION", (signal, reasons)
    assert any("offering" in r.lower() for r in reasons)


def test_conversion_excluded_from_cluster_buy():
    conn = make_db()
    _load_clbk_conversion(conn)
    mark_offering_purchases(conn, CFG)
    # None of the conversion filings should read as a cluster buy.
    for i in range(5):
        signal, _ = classify_filing(conn, CFG, f"clbk-{i}")
        assert signal == "OFFERING PARTICIPATION", (i, signal)


def test_genuine_cluster_buy_still_bullish():
    """Different insiders buying at DIFFERENT prices is a real open-market
    cluster — must stay STRONG BULLISH, not be swept up as an offering."""
    conn = make_db()
    for i, price in enumerate([31.20, 32.05, 30.88]):
        p = _buy_filing(f"000000220{i}", f"BUYER {i}", price, "2026-07-21",
                        issuer="0000900002", ticker="REAL")
        store_filing(conn, p, f"real-{i}", "2026-07-21", "u")
    flagged = mark_offering_purchases(conn, CFG)
    assert flagged == 0, "distinct prices must not be flagged as an offering"
    signal, reasons = classify_filing(conn, CFG, "real-0")
    assert signal == "STRONG BULLISH", (signal, reasons)
    assert any("cluster buy" in r for r in reasons)


def test_new_issue_window_flags_varying_price_conversion():
    """Condition 2: a clustered conversion whose subscription price varies by a
    cent (so condition 1's exact-price match misses it) is still flagged when
    the issuer is a recent listing."""
    conn = make_db()
    for i, price in enumerate([10.00, 10.01, 9.99, 10.02]):
        p = _buy_filing(f"330{i:02d}", f"NEW {i}", price, "2026-07-21",
                        issuer="0000900003", ticker="NEWIPO")
        store_filing(conn, p, f"ipo-{i}", "2026-07-21", "u")
    cfg = {"signals": dict(CFG["signals"], check_new_issue=True)}
    # Inject the new-issue check so the test does not hit the network.
    flagged = mark_offering_purchases(
        conn, cfg, new_issue_check=lambda tk, d, n: tk == "NEWIPO"
    )
    assert flagged == 4, flagged
    assert classify_filing(conn, CFG, "ipo-0")[0] == "OFFERING PARTICIPATION"


def test_new_issue_check_not_triggered_for_established_issuer():
    """A same-day cluster at DIFFERENT prices on an ESTABLISHED (non-new-issue)
    issuer stays a real cluster buy — condition 2 must not sweep it up."""
    conn = make_db()
    for i, price in enumerate([44.10, 45.02, 43.88]):
        p = _buy_filing(f"440{i:02d}", f"BUYER {i}", price, "2026-07-21",
                        issuer="0000900004", ticker="OLDCO")
        store_filing(conn, p, f"old-{i}", "2026-07-21", "u")
    cfg = {"signals": dict(CFG["signals"], check_new_issue=True)}
    flagged = mark_offering_purchases(
        conn, cfg, new_issue_check=lambda tk, d, n: False  # not a new issue
    )
    assert flagged == 0
    assert classify_filing(conn, CFG, "old-0")[0] == "STRONG BULLISH"


def test_offering_summary_groups_by_issuer():
    conn = make_db()
    _load_clbk_conversion(conn)
    mark_offering_purchases(conn, CFG)
    summary = insider_radar.offering_summary(conn, "2026-01-01")
    assert len(summary) == 1
    assert summary[0]["ticker"] == "CLBK"
    assert summary[0]["insiders"] == 5
    assert summary[0]["price"] == 10.00


if __name__ == "__main__":
    import traceback
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"PASS {name}")
            except Exception:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
