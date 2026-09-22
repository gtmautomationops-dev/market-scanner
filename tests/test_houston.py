"""
Unit tests for Houston's (mission control) pure logic.

Covers the ETF lens (universe build, ranking, fresh-idea selection, held-ETF
health), the fund-wide risk roll-up (reusing Sarah's rules), and the desk
roll-call (runlog summarization + staleness labelling). All offline — prices are
synthetic {ticker: (closes, volumes)} dicts and desk logs are plain dicts, so
there is no network, no yfinance, and no filesystem read.

Run with:  python -m pytest tests/test_houston.py
       or:  python tests/test_houston.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import houston

# Keep these tests fully offline: display_name() would otherwise reach yfinance
# for a human-readable ETF name. The ticker itself is a fine stand-in here.
houston.display_name = lambda t: t


def _series(start, end, n=140):
    """Linear price path from start to end over n bars."""
    step = (end - start) / (n - 1)
    return [round(start + step * i, 4) for i in range(n)]


def _vols(n=140, v=1_000_000):
    return [float(v)] * n


# ─── ETF universe / classification ────────────────────────────────────────────

def test_etf_universe_respects_toggles():
    base = houston.etf_universe({"exclude_leveraged": True, "include_bond_etfs": True,
                                 "include_canada": True})
    assert "SPY" in base
    assert "TQQQ" not in base           # leveraged excluded
    assert "TLT" in base                # bond ETF kept
    assert any(t.endswith(".TO") for t in base)  # Canada included

    no_bonds = houston.etf_universe({"include_bond_etfs": False})
    assert "TLT" not in no_bonds
    assert "SPY" in no_bonds

    us_only = houston.etf_universe({"include_canada": False})
    assert not any(t.endswith(".TO") for t in us_only)


def test_is_etf():
    assert houston.is_etf("SPY") is True
    assert houston.is_etf("XLK") is True
    assert houston.is_etf("AAPL") is False


# ─── ranking ──────────────────────────────────────────────────────────────────

def test_rank_etfs_orders_best_first():
    bench = _series(100, 105)
    prices = {
        "SPY": (_series(80, 130), _vols()),   # strong uptrend
        "XLK": (_series(120, 85), _vols()),   # downtrend
    }
    ranked = houston.rank_etfs(prices, ["SPY", "XLK"], bench)
    assert [r["ticker"] for r in ranked] == ["SPY", "XLK"]
    assert ranked[0]["score"] > ranked[1]["score"]


def test_rank_etfs_skips_unpriced():
    ranked = houston.rank_etfs({"SPY": (_series(80, 130), _vols())},
                               ["SPY", "QQQ"], None)
    assert [r["ticker"] for r in ranked] == ["SPY"]  # QQQ had no data


# ─── fresh ideas ──────────────────────────────────────────────────────────────

def _ranked_stub(ticker, score):
    """A ranked-row shape with a real closes list so plan_trade can run."""
    return {"ticker": ticker, "score": score, "price": 100.0,
            "factors": [f"+{score:.2f} synthetic"], "closes": _series(80, 100)}


def test_etf_ideas_skips_held_and_applies_threshold():
    ranked = [_ranked_stub("SPY", 8.0), _ranked_stub("XLK", 6.0), _ranked_stub("QQQ", 1.0)]
    profile = {"initial_stop_pct": 0.08, "target_r": 2.5}

    ideas = houston.etf_ideas(ranked, held={"SPY"}, min_score=4.0, top_n=10,
                              plan_profile=profile)
    tickers = [i["ticker"] for i in ideas]
    assert "SPY" not in tickers          # held → skipped
    assert "XLK" in tickers              # unheld, above threshold
    assert "QQQ" not in tickers          # below min_score
    assert ideas[0]["plan"]["target"] > ideas[0]["plan"]["entry"] > ideas[0]["plan"]["stop"]


def test_etf_ideas_caps_at_top_n():
    ranked = [_ranked_stub(t, 9.0) for t in ("SPY", "QQQ", "XLK", "IWM")]
    ideas = houston.etf_ideas(ranked, held=set(), min_score=1.0, top_n=2,
                              plan_profile={"initial_stop_pct": 0.08, "target_r": 2.5})
    assert len(ideas) == 2


# ─── held ETF health ──────────────────────────────────────────────────────────

def test_held_etf_health_only_etfs_and_verdicts():
    ranked = [_ranked_stub("SPY", 9.0), _ranked_stub("XLK", 1.0)]
    positions = [
        {"symbol": "SPY", "book": "My Picks", "unreal_pct": 5.0},   # ETF, leading
        {"symbol": "XLK", "book": "Momentum", "unreal_pct": -2.0},  # ETF, fading
        {"symbol": "AAPL", "book": "My Picks", "unreal_pct": 3.0},  # not an ETF
    ]
    health = houston.held_etf_health(positions, ranked, min_score=4.0)
    syms = {h["symbol"] for h in health}
    assert syms == {"SPY", "XLK"}                     # AAPL excluded
    spy = next(h for h in health if h["symbol"] == "SPY")
    xlk = next(h for h in health if h["symbol"] == "XLK")
    assert spy["verdict"] == "leading the ETF pack"
    assert "fading" in xlk["verdict"]


# ─── fund-wide risk (reuses Sarah's rules) ────────────────────────────────────

def test_fund_risk_flags_stop_breach_and_concentration():
    cfg = {"near_stop_pct": 3, "loss_alert_pct": 12, "concentration_pct": 25}
    positions = [
        # below its stop → an act-now alert; also a big single-name weight
        {"symbol": "SPY", "book": "My Picks", "price": 89.0, "stop": 90.0,
         "target": 130.0, "unreal_pct": -11.0, "days_held": 5, "mv": 9000.0},
        {"symbol": "AAPL", "book": "Momentum", "price": 50.0, "stop": 40.0,
         "target": 80.0, "unreal_pct": 2.0, "days_held": 5, "mv": 1000.0},
    ]
    checklist, n_alert, n_watch, mom_dd = houston.fund_risk(
        positions, total_exposure=10000.0,
        momentum_curve_values=[10000, 12000, 10600], cfg=cfg)

    codes = {(c["symbol"], c["code"]) for c in checklist}
    assert ("SPY", "stop_breached") in codes
    assert ("SPY", "concentration") in codes         # 90% of the book
    assert n_alert >= 1
    assert checklist[0]["level"] == "alert"          # alerts sort first
    spy_row = next(c for c in checklist if c["symbol"] == "SPY")
    assert spy_row["is_etf"] is True
    assert mom_dd < 0                                 # 10600 is below the 12000 peak


# ─── desk roll-call: age + summarization ──────────────────────────────────────

def test_age_hours_and_label():
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    two_h = (now - timedelta(hours=2)).isoformat()
    assert round(houston.age_hours(two_h, now), 3) == 2.0
    assert houston.age_hours(None, now) is None

    assert houston.age_label(None) == "never"
    assert houston.age_label(2) == "2h ago"
    assert houston.age_label(72) == "3d ago"


def test_summarize_desk_sarah_levels():
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(hours=1)).isoformat()

    alerting = houston.summarize_desk(
        "risk_sarah",
        {"run_at": recent, "alerts": 2, "watches": 1, "positions_reviewed": 3,
         "momentum_drawdown_pct": -9.7},
        now, stale_hours=48)
    assert alerting["level"] == "alert"
    assert alerting["filed"] is True and alerting["stale"] is False
    assert "2 alerts" in alerting["headline"]

    calm = houston.summarize_desk(
        "risk_sarah", {"run_at": recent, "alerts": 0, "watches": 0,
                       "positions_reviewed": 3}, now, stale_hours=48)
    assert calm["level"] == "ok"


def test_summarize_desk_missing_and_stale():
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

    missing = houston.summarize_desk("congress", None, now, stale_hours=48)
    assert missing["filed"] is False
    assert missing["stale"] is True
    assert missing["age_label"] == "never"

    old = (now - timedelta(hours=100)).isoformat()
    stale = houston.summarize_desk(
        "momentum_trader",
        {"run_at": old, "equity": 9000, "open_positions": 2, "closed_this_run": 0,
         "risk_profile": "normal", "errors": []},
        now, stale_hours=48)
    assert stale["filed"] is True
    assert stale["stale"] is True
    assert "paper equity" in stale["headline"]


def test_summarize_desk_flags_errors_as_alert():
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(hours=1)).isoformat()
    errored = houston.summarize_desk(
        "insider_radar",
        {"run_at": recent, "form4_in_window": 0, "stored": 0,
         "offering_purchases_flagged": 5, "errors": ["boom"]},
        now, stale_hours=48)
    assert errored["level"] == "alert"
    assert "error" in errored["headline"]


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
        except Exception:
            failed += 1
            print(f"  FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
