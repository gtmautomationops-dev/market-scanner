"""
Unit tests for the deterministic pieces of the Momentum Trader:
momentum scoring, trade planning, and trailing-stop management.

These exercise pure functions only — no network, no yfinance calls.
Run with:  python -m pytest tests/test_momentum_trader.py
       or:  python tests/test_momentum_trader.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import momentum_trader as mt


# ─── momentum_score ───────────────────────────────────────────────────────────

def _uptrend(n=260, start=50.0, daily=0.004):
    """A clean, steadily rising series."""
    return [start * (1 + daily) ** i for i in range(n)]


def _downtrend(n=260, start=100.0, daily=0.004):
    return [start * (1 - daily) ** i for i in range(n)]


def test_score_ranks_uptrend_above_downtrend():
    vols = [1_000_000] * 260
    up, _ = mt.momentum_score(_uptrend(), vols)
    down, _ = mt.momentum_score(_downtrend(), vols)
    assert up > down
    assert up > 0
    assert down < 0


def test_score_returns_none_on_short_history():
    score, factors = mt.momentum_score([10, 11, 12], [100, 100, 100])
    assert score is None
    assert factors == []


def test_score_factors_are_explained():
    _, factors = mt.momentum_score(_uptrend(), [1_000_000] * 260)
    assert factors, "expected named factor contributions"
    # Each factor is a signed, human-readable contribution string.
    assert all(f[0] in "+-" for f in factors)


def test_volume_expansion_helps_score():
    closes = _uptrend()
    flat_vol = [1_000_000] * 260
    rising_vol = [1_000_000] * 240 + [2_000_000] * 20  # last 20d well above 60d avg
    base, _ = mt.momentum_score(closes, flat_vol)
    boosted, _ = mt.momentum_score(closes, rising_vol)
    assert boosted > base


# ─── plan_trade ───────────────────────────────────────────────────────────────

PROFILE = {
    "name": "normal", "deploy_fraction": 0.5, "initial_stop_pct": 0.08,
    "activate_pct": 0.06, "trail_pct": 0.06, "target_r": 2.5,
    "min_momentum": 4.0, "max_positions": 3,
}


def test_plan_trade_stop_respects_floor():
    closes = _uptrend()  # very low ATR, so the floor should bind
    plan = mt.plan_trade(closes[-1], closes, PROFILE)
    # Stop is never tighter than the profile floor and never looser than 20%.
    assert plan["stop"] <= plan["entry"]
    assert 8.0 <= plan["stop_pct"] <= 20.0


def test_plan_trade_target_is_r_multiple_of_risk():
    closes = _uptrend()
    plan = mt.plan_trade(closes[-1], closes, PROFILE)
    risk = plan["entry"] - plan["stop"]
    expected_target = plan["entry"] + PROFILE["target_r"] * risk
    assert abs(plan["target"] - expected_target) < 0.02
    assert plan["target"] > plan["entry"]


# ─── manage_position ──────────────────────────────────────────────────────────

def _pos(entry=100.0, stop=92.0, peak=100.0, target=120.0, armed=0):
    return {
        "entry_price": entry, "initial_stop": stop, "stop": stop,
        "peak": peak, "target": target, "armed": armed,
    }


def test_stop_loss_triggers_below_stop():
    reason, *_ = mt.manage_position(_pos(), price=90.0, profile=PROFILE)
    assert reason == "stop loss"


def test_stop_arms_to_breakeven_after_activation():
    # +7% > activate_pct (6%) arms the stop; it should jump to >= breakeven.
    reason, new_stop, peak, armed = mt.manage_position(_pos(), price=107.0, profile=PROFILE)
    assert reason is None
    assert armed is True
    assert new_stop >= 100.0  # breakeven or better


def test_trailing_stop_ratchets_up_and_never_down():
    # First arm and trail from a high peak.
    _, stop_high, _, _ = mt.manage_position(_pos(peak=100.0), price=120.0, profile=PROFILE)
    # A later, lower price must not lower the already-raised stop.
    pos = _pos(stop=stop_high, peak=120.0, armed=1)
    _, stop_after, _, _ = mt.manage_position(pos, price=115.0, profile=PROFILE)
    assert stop_after >= stop_high


def test_profit_target_triggers():
    reason, *_ = mt.manage_position(_pos(target=120.0), price=121.0, profile=PROFILE)
    assert reason == "profit target"


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
