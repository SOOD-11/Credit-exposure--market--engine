"""Position valuation. Values are always *to the client* (positive = client is in the money)."""
import numpy as np
import pandas as pd
from .bs import bs_price
from .config import RISK_FREE_RATE, TRADING_DAYS


def trailing_vol(prices, idx, window=252):
    """Annualised volatility from log returns over the `window` days ending at row `idx` (no look-ahead)."""
    lr = np.log(prices.iloc[idx - window: idx + 1]).diff().dropna()
    return lr.std() * np.sqrt(TRADING_DAYS)


def unit_values(pos, S, vol, date, shift=0.0, r=RISK_FREE_RATE):
    """Value of ONE unit of each position under every row of S (scenarios x tickers).

    SWAP  -> the stock price itself (client is long the stock via a total-return swap with the bank)
    PUT / CALL -> Black-Scholes price. Time to expiry shrinks by `shift` years (time decay over the margin period).
    Returns array (n_scenarios x n_positions).
    """
    out = np.empty((len(S), len(pos)))
    for j, p in enumerate(pos.itertuples()):
        s = S[p.ticker].to_numpy(dtype=float)
        if p.instrument == "SWAP":
            out[:, j] = s
        else:
            T = max((pd.Timestamp(p.expiry) - pd.Timestamp(date)).days / 365.0 - shift, 0.0)
            out[:, j] = bs_price(s, p.strike, T, r, vol[p.ticker], p.instrument.lower())
    return out


def portfolio_value(pos, S, vol, date, shift=0.0):
    """Total value to the client under each scenario row of S."""
    return unit_values(pos, S, vol, date, shift) @ pos["qty"].to_numpy(dtype=float)
