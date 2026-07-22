"""Tests for the House PTR parser using real filing text fixtures."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from congress_ptr_parser import parse_ptr_text, public_transactions

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- header

def test_parse_member_identity():
    p = parse_ptr_text(load("ptr_alford_basket.txt"))
    assert p["filing_id"] == "20034201"
    assert "Alford" in p["member_name"]
    assert p["state_district"] == "MO04"
    assert p["state"] == "MO"
    assert p["district"] == 4


# ---------------------------------------------------------------- single buy

def test_single_stock_purchase():
    p = parse_ptr_text(load("ptr_single_defense_buy.txt"))
    assert p["state_district"] == "TX22"
    pub = public_transactions(p)
    assert len(pub) == 1
    t = pub[0]
    assert t["ticker"] == "LMT"
    assert t["tx_type"] == "P"
    assert t["tx_type_label"] == "Purchase"
    assert t["partial"] is False
    assert t["tx_date"] == "05/12/2026"
    assert t["amount_low"] == 250001
    assert t["amount_high"] == 500000  # amount wrapped to next line; must re-join


# ---------------------------------------------------------------- basket sale

def test_basket_sale_attributes_named_stocks():
    p = parse_ptr_text(load("ptr_alford_basket.txt"))
    pub = public_transactions(p)
    tickers = {t["ticker"] for t in pub}
    # Named single-name stocks must be correctly attributed
    for expected in ("AMZN", "AAPL", "T", "BRK.B", "PYPL"):
        assert expected in tickers, f"missing {expected}: got {tickers}"
    # All are partial sales in this filing
    assert all(t["tx_type"] == "S" for t in pub)
    assert all(t["partial"] for t in pub)


# ---------------------------------------------------------------- private asset

def test_private_asset_has_no_ticker():
    p = parse_ptr_text(load("ptr_begich_private.txt"))
    assert "Begich" in p["member_name"]
    # The single asset is a private company (Physical Superintelligence) with
    # no ticker; it must be parsed but carry ticker=None, and be excluded from
    # public_transactions.
    assert len(public_transactions(p)) == 0
    assert any(t["ticker"] is None for t in p["transactions"])


def test_amount_range_parsed_as_ints():
    p = parse_ptr_text(load("ptr_begich_private.txt"))
    t = p["transactions"][0]
    assert t["amount_low"] == 100001
    assert t["amount_high"] == 250000
    assert t["tx_type"] == "E"


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
