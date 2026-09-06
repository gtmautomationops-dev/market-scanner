"""
Unit tests for the hedge-fund agents' pure logic (Alex / Sarah / Elena).

Covers the marking, risk-flagging, and report-aggregation math in fund_common
and report_elena. All offline — prices are passed in as synthetic
{ticker: (closes, volumes)} dicts, so there is no network or yfinance call.

Run with:  python -m pytest tests/test_hedge_fund.py
       or:  python tests/test_hedge_fund.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fund_common as fc
import report_elena as elena
import flow_marcus as flow


def _prices(**last):
    """Build a prices dict where each ticker's last close is the given value."""
    return {t: ([v - 1, v], [1_000_000, 1_000_000]) for t, v in last.items()}


# ─── mark_my_picks ─────────────────────────────────────────────────────────────

def test_mark_my_picks_pnl_math():
    holdings = {"benchmark": "SPY",
                "open": [{"symbol": "AAA", "shares": 10, "entry_price": 100.0,
                          "entry_date": "2026-01-01", "stop": 90.0, "target": 130.0,
                          "note": ""}],
                "closed": [{"symbol": "BBB", "shares": 5, "entry_price": 20.0,
                            "entry_date": "2025-12-01", "exit_price": 30.0,
                            "exit_date": "2026-01-15", "stop": None, "target": None,
                            "note": ""}]}
    book = fc.mark_my_picks(holdings, _prices(AAA=120.0), today=date(2026, 2, 1))
    pos = book["positions"][0]
    assert pos["mv"] == 1200.0            # 10 * 120
    assert pos["unreal"] == 200.0         # (120 - 100) * 10
    assert pos["r_now"] == 2.0            # (120-100)/(100-90)
    assert book["cost_basis"] == 1000.0
    assert book["unrealized"] == 200.0
    assert book["realized"] == 50.0       # (30 - 20) * 5
    assert book["total_pnl"] == 250.0


def test_mark_my_picks_missing_price_marks_flat():
    holdings = {"benchmark": "SPY",
                "open": [{"symbol": "ZZZ", "shares": 3, "entry_price": 50.0,
                          "entry_date": None, "stop": None, "target": None, "note": ""}],
                "closed": []}
    book = fc.mark_my_picks(holdings, _prices())  # no price for ZZZ
    assert book["positions"][0]["price"] == 50.0  # falls back to entry
    assert book["unrealized"] == 0.0
    assert book["positions"][0]["priced"] is False


def test_load_holdings_drops_malformed_lots(tmp_path=None):
    import textwrap, tempfile, os
    y = textwrap.dedent("""
        benchmark: qqq
        holdings:
          - symbol: GOOD
            shares: 10
            entry_price: 5
          - symbol: BADNOSHARES
            entry_price: 5
          - shares: 3
            entry_price: 2
        closed: []
    """)
    fd, path = tempfile.mkstemp(suffix=".yml")
    os.write(fd, y.encode()); os.close(fd)
    try:
        h = fc.load_holdings(path)
    finally:
        os.unlink(path)
    assert h["benchmark"] == "QQQ"
    assert [l["symbol"] for l in h["open"]] == ["GOOD"]  # the other two are dropped


# ─── Sarah's risk rules ────────────────────────────────────────────────────────

CFG = {"near_stop_pct": 3, "near_target_pct": 3, "loss_alert_pct": 12,
       "stale_days": 30, "stale_flat_band": 5, "concentration_pct": 25,
       "drawdown_alert_pct": 10}


def _pos(**kw):
    base = {"symbol": "X", "price": 100.0, "stop": None, "target": None,
            "unreal_pct": 0.0, "days_held": 1, "mv": 1000.0, "book": "My Picks"}
    base.update(kw)
    return base


def test_flag_stop_breached_is_alert():
    flags = fc.position_flags(_pos(price=89.0, stop=90.0, unreal_pct=-11.0), CFG)
    codes = {(f["level"], f["code"]) for f in flags}
    assert ("alert", "stop_breached") in codes


def test_flag_near_stop_is_watch():
    flags = fc.position_flags(_pos(price=92.0, stop=90.0), CFG)  # within 3%
    assert any(f["code"] == "near_stop" and f["level"] == "watch" for f in flags)


def test_flag_target_hit_and_big_loss():
    hit = fc.position_flags(_pos(price=131.0, target=130.0), CFG)
    assert any(f["code"] == "target_hit" for f in hit)
    loss = fc.position_flags(_pos(price=80.0, unreal_pct=-20.0), CFG)
    assert any(f["code"] == "big_loss" and f["level"] == "alert" for f in loss)


def test_flag_stale_flat_position():
    flags = fc.position_flags(_pos(unreal_pct=1.0, days_held=45), CFG)
    assert any(f["code"] == "stale" for f in flags)
    # A big mover held just as long is NOT stale.
    moving = fc.position_flags(_pos(unreal_pct=30.0, days_held=45), CFG)
    assert not any(f["code"] == "stale" for f in moving)


def test_clean_position_has_no_flags():
    assert fc.position_flags(_pos(price=105.0, stop=90.0, target=200.0,
                                  unreal_pct=5.0, days_held=3), CFG) == []


def test_concentration_flag():
    positions = [_pos(symbol="BIG", mv=800.0), _pos(symbol="SMALL", mv=200.0)]
    flags = fc.concentration_flags(positions, 1000.0, CFG)
    assert [f["symbol"] for f in flags] == ["BIG"]  # 80% >= 25%
    assert flags[0]["weight"] == 80.0


def test_drawdown_from_peak():
    assert fc.drawdown_from_peak([100, 120, 90]) == -25.0   # peak 120 -> 90
    assert fc.drawdown_from_peak([100, 110, 130]) == 0.0    # at highs
    assert fc.drawdown_from_peak([]) == 0.0


# ─── Elena's aggregation ───────────────────────────────────────────────────────

def _momentum_book(curve):
    return {"starting": 10000.0, "curve": curve, "total_pnl": 0.0, "return_pct": 0.0,
            "positions": [], "trades": [], "positions_value": 0.0, "total_equity": 10000.0}


def test_combined_curve_forward_fills():
    mom = _momentum_book([
        {"snap_date": "2026-01-01", "total_equity": 10000.0, "benchmark_price": 100.0},
        {"snap_date": "2026-01-03", "total_equity": 10200.0, "benchmark_price": 110.0},
    ])
    mp_curve = [{"snap_date": "2026-01-02", "total_pnl": 50.0, "benchmark_price": 105.0}]
    rows, bench = elena.build_combined_curve(mom, mp_curve)
    dates = [r["date"] for r in rows]
    assert dates == ["2026-01-01", "2026-01-02", "2026-01-03"]
    # On 01-02 momentum has no snapshot -> forward-filled to +0; my picks +50.
    r2 = next(r for r in rows if r["date"] == "2026-01-02")
    assert r2["combined"] == 50.0
    # On 01-03 momentum is +200, my picks forward-filled to +50 -> +250.
    r3 = next(r for r in rows if r["date"] == "2026-01-03")
    assert r3["combined"] == 250.0


def test_week_delta_uses_seven_day_lookback():
    rows = [
        {"date": "2026-01-01", "combined": 0.0},
        {"date": "2026-01-05", "combined": 100.0},
        {"date": "2026-01-12", "combined": 300.0},
    ]
    delta, base = elena._week_delta(rows)
    assert base == "2026-01-05"     # closest snapshot <= 7 days before 01-12
    assert delta == 200.0


def test_week_delta_empty():
    assert elena._week_delta([]) == (0.0, None)


# ─── Marcus's options-flow logic ───────────────────────────────────────────────

FLOW_CFG = {"min_volume": 500, "min_vol_oi_ratio": 1.5, "min_notional": 250000,
            "min_dte": 3, "max_dte": 60}


def _mk(typ="call", spot=100.0, strike=105.0, dte=14, last=3.0, ask=3.0,
        volume=3000, oi=500):
    return flow._contract(symbol="X", spot=spot, typ=typ, strike=strike, expiry="2026-09-20",
                          dte=dte, last=last, bid=last - 0.1, ask=ask, volume=volume,
                          open_interest=oi, iv=0.5)


def test_contract_notional_and_vol_oi():
    c = _mk(volume=3000, oi=500, ask=3.0)
    assert c["notional"] == 3000 * 3.0 * 100          # 900,000
    assert c["vol_oi"] == 6.0
    # Zero OI -> infinite vol/OI (brand-new positioning).
    assert _mk(oi=0)["vol_oi"] == float("inf")


def test_contract_moneyness_sign():
    call_otm = _mk("call", spot=100, strike=110)["otm"]   # +10% OTM
    put_otm = _mk("put", spot=100, strike=90)["otm"]      # +10% OTM
    assert round(call_otm, 3) == 0.1
    assert round(put_otm, 3) == 0.1
    assert _mk("call", spot=100, strike=90)["otm"] < 0    # ITM call


def test_score_rewards_fresh_aggressive_prints():
    aggressive = _mk(volume=6000, oi=300, ask=5.0, dte=14, strike=105)  # 5x OI, $3M
    tame = _mk(volume=600, oi=4000, ask=0.5, dte=14, strike=105)        # below OI, small
    sa, _ = flow.score_contract(aggressive)
    st, _ = flow.score_contract(tame)
    assert sa > st
    assert sa > 0


def test_passes_criteria_gate():
    good = _mk(volume=3000, oi=500, ask=3.0, dte=14)   # 900K notional, 6x OI
    assert flow.passes_criteria(good, FLOW_CFG)
    thin = _mk(volume=300, oi=500, ask=3.0, dte=14)    # below min_volume
    assert not flow.passes_criteria(thin, FLOW_CFG)
    closing = _mk(volume=3000, oi=5000, ask=3.0)       # vol/OI 0.6 < 1.5
    assert not flow.passes_criteria(closing, FLOW_CFG)
    far = _mk(volume=3000, oi=500, ask=3.0, dte=200)   # outside DTE band
    assert not flow.passes_criteria(far, FLOW_CFG)


def test_defined_risk_play_caps_loss():
    call = _mk("call", spot=100, strike=105, ask=3.0)
    play = flow.defined_risk_play(call)
    assert play["max_loss"] == play["debit_per_contract"] == 300.0  # 3.0 * 100
    assert play["breakeven"] == 108.0                                # 105 + 3
    put = flow.defined_risk_play(_mk("put", spot=100, strike=95, ask=2.0))
    assert put["breakeven"] == 93.0                                  # 95 - 2


def test_flow_sentiment_tilt():
    contracts = [
        flow._contract("AAA", 100, "call", 105, "2026-09-20", 14, 4, 3.9, 4.0, 5000, 100, 0.5),
        flow._contract("AAA", 100, "put", 95, "2026-09-20", 14, 1, 0.9, 1.0, 200, 100, 0.5),
    ]
    s = flow.flow_sentiment(contracts)[0]
    assert s["symbol"] == "AAA"
    assert s["tilt"] == "bullish"        # call premium dwarfs put premium
    assert s["call_pct"] >= 65


def test_get_provider_selection():
    assert isinstance(flow.get_provider({"data_source": "yfinance"}), flow.YFinanceProvider)
    # Paid providers resolve but their fetch is a not-yet-wired stub.
    poly = flow.get_provider({"data_source": "polygon"})
    assert isinstance(poly, flow.PolygonProvider)
    try:
        poly.unusual_contracts(["NVDA"], {})
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass
    # Unknown source is a hard error, not a silent default.
    try:
        flow.get_provider({"data_source": "bogus"})
        assert False, "expected ValueError"
    except ValueError:
        pass


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
