"""Black-Scholes pricing and Greeks (European options, no dividends)."""
import numpy as np
from scipy.stats import norm


def _d1_d2(S, K, T, r, sigma):
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    T_ = np.maximum(T, 1e-10)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T_) / (sigma * np.sqrt(T_))
    return d1, d1 - sigma * np.sqrt(T_), T_


def bs_price(S, K, T, r, sigma, kind):
    """Option price. kind is 'call' or 'put'. At T<=0 returns intrinsic value."""
    d1, d2, T_ = _d1_d2(S, K, T, r, sigma)
    S, K = np.asarray(S, dtype=float), np.asarray(K, dtype=float)
    if kind == "call":
        px = S * norm.cdf(d1) - K * np.exp(-r * T_) * norm.cdf(d2)
        intrinsic = np.maximum(S - K, 0.0)
    elif kind == "put":
        px = K * np.exp(-r * T_) * norm.cdf(-d2) - S * norm.cdf(-d1)
        intrinsic = np.maximum(K - S, 0.0)
    else:
        raise ValueError("kind must be 'call' or 'put'")
    return np.where(np.asarray(T) <= 0, intrinsic, px)


def bs_greeks(S, K, T, r, sigma, kind):
    """Delta, gamma, vega (per 1.00 = 100 vol points; divide by 100 for per-vol-point)."""
    d1, _, T_ = _d1_d2(S, K, T, r, sigma)
    S, sigma = np.asarray(S, dtype=float), np.asarray(sigma, dtype=float)
    delta = norm.cdf(d1) if kind == "call" else norm.cdf(d1) - 1.0
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T_))
    vega = S * norm.pdf(d1) * np.sqrt(T_)
    return {"delta": delta, "gamma": gamma, "vega": vega}
