import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from risk_engine.bs import bs_price, bs_greeks
from risk_engine.backtest import kupiec_pof
from risk_engine.config import MarginParams
from risk_engine.exposure import current_exposure, margin_call, potential_exposure
from risk_engine.margin import initial_margin, concentration_scales


# ---------- Black-Scholes ----------
def test_put_call_parity():
    S, K, T, r, s = 100.0, 95.0, 0.5, 0.04, 0.3
    c, p = bs_price(S, K, T, r, s, "call"), bs_price(S, K, T, r, s, "put")
    assert c - p == pytest.approx(S - K * np.exp(-r * T), abs=1e-9)


def test_greeks_match_finite_differences():
    S, K, T, r, s = 100.0, 95.0, 0.5, 0.04, 0.3
    h = 1e-3
    g = bs_greeks(S, K, T, r, s, "put")
    d = (bs_price(S + h, K, T, r, s, "put") - bs_price(S - h, K, T, r, s, "put")) / (2 * h)
    gam = (bs_price(S + h, K, T, r, s, "put") - 2 * bs_price(S, K, T, r, s, "put") + bs_price(S - h, K, T, r, s, "put")) / h**2
    v = (bs_price(S, K, T, r, s + h, "put") - bs_price(S, K, T, r, s - h, "put")) / (2 * h)
    assert float(g["delta"]) == pytest.approx(float(d), abs=1e-5)
    assert float(g["gamma"]) == pytest.approx(float(gam), abs=1e-4)
    assert float(g["vega"]) == pytest.approx(float(v), abs=1e-3)


def test_expired_option_is_intrinsic():
    assert float(bs_price(90.0, 100.0, 0.0, 0.04, 0.3, "put")) == pytest.approx(10.0)


# ---------- exposure / margin call logic ----------
def test_exposure_logic():
    assert current_exposure(total_mtm=-5e6, collateral=2e6) == 3e6      # owes 5m, holds 2m -> 3m uncovered
    assert current_exposure(total_mtm=-1e6, collateral=2e6) == 0.0      # fully covered
    assert current_exposure(total_mtm=4e6, collateral=0.0) == 0.0       # client in the money
    assert margin_call(initial_margin=6e6, collateral=4e6) == 2e6
    assert margin_call(initial_margin=3e6, collateral=4e6) == 0.0
    assert potential_exposure(total_mtm=1e6, collateral=2e6, initial_margin=6e6) == 3e6   # -(1-6) - 2


# ---------- margin on a hand-checkable portfolio ----------
def _prices(n=40):
    """One stock whose price is 100 for the first 30 days, then makes known jumps."""
    px = np.full(n, 100.0)
    return pd.DataFrame({"XYZ": px}, index=pd.bdate_range("2020-01-01", periods=n))


def test_margin_single_stock_hand_checked():
    # price path: 100, 100, ..., with a single 10% drop at row 20 and flat afterwards
    p = _prices()
    p.iloc[20:, 0] = 90.0
    params = MarginParams(confidence=0.99, horizon=5, lookback=30, vol_window=10, conc_threshold=2.0)
    pos = pd.DataFrame([dict(ticker="XYZ", instrument="SWAP", qty=1000.0, strike=np.nan, expiry=pd.NaT, entry_value=100.0)])
    idx = 35
    res = initial_margin(pos, p, idx, params)
    # 5-day windows that straddle row 20 lose 10%: loss = 1000 * 90 * ... scenario applies -10% to today's price (90):
    # today's spot = 90 -> loss per scenario = 1000 * 90 * 0.10 = 9000, in the worst windows.
    assert res["im"] == pytest.approx(9000.0, rel=1e-9)
    assert res["es"] == pytest.approx(9000.0, rel=1e-9)
    assert res["n_scen"] == 30 + 1 - 5


def test_margin_has_no_lookahead():
    rng = np.random.default_rng(0)
    p = pd.DataFrame({"XYZ": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800)))}, index=pd.bdate_range("2018-01-01", periods=800))
    params = MarginParams(horizon=10, lookback=300, vol_window=100)
    pos = pd.DataFrame([dict(ticker="XYZ", instrument="SWAP", qty=500.0, strike=np.nan, expiry=pd.NaT, entry_value=100.0)])
    idx = 500
    a = initial_margin(pos, p, idx, params)["im"]
    p2 = p.copy()
    p2.iloc[idx + 1:, 0] *= 3.0           # wildly change the FUTURE
    b = initial_margin(pos, p2, idx, params)["im"]
    assert a == b


def test_concentration_scaling_flags_big_name():
    spot = pd.Series({"A": 100.0, "B": 100.0})
    pos = pd.DataFrame([dict(ticker="A", instrument="SWAP", qty=900.0, strike=np.nan),
                        dict(ticker="B", instrument="SWAP", qty=100.0, strike=np.nan)])
    scales, w = concentration_scales(pos, spot, MarginParams(conc_threshold=0.25))
    assert scales["A"] > 1.0 and scales["B"] == 1.0
    assert w["A"] == pytest.approx(0.9)


# ---------- Kupiec ----------
def test_kupiec_known_values():
    lr, p = kupiec_pof(n=250, x=0, p=0.01)
    assert lr == pytest.approx(-2 * 250 * np.log(0.99), rel=1e-9)
    lr2, p2 = kupiec_pof(n=250, x=8, p=0.01)
    assert p2 < 0.05                       # 8 exceptions in 250 days (expected 2.5) is too many for a 99% model
    lr3, p3 = kupiec_pof(n=250, x=2, p=0.01)
    assert p3 > 0.05
