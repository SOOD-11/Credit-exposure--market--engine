"""Initial margin by historical simulation.

Idea (plain English): if the client defaults today, the bank needs ~10 trading days to close out the portfolio.
So we ask: "over any 10-day window in the last 2 years, how much would TODAY's portfolio have lost?"
Initial margin (IM) = the 99th-percentile of those losses. Expected Shortfall (ES) = the average loss in the worst 1%.
Only data up to the as-of date is used (no look-ahead).
"""
import numpy as np
import pandas as pd
from .config import PARAMS
from .valuation import trailing_vol, portfolio_value


def concentration_scales(pos, spot, params=PARAMS):
    """Scale factor per ticker: names above the concentration threshold get larger scenario moves."""
    gross = {}
    for p in pos.itertuples():
        n = abs(p.qty) * (spot[p.ticker] if p.instrument == "SWAP" else p.strike)
        gross[p.ticker] = gross.get(p.ticker, 0.0) + n
    g = pd.Series(gross)
    w = g / g.sum()
    return w.map(lambda x: params.conc_scale if x > params.conc_threshold else 1.0), w


def scenario_returns(prices, idx, params=PARAMS):
    """Overlapping `horizon`-day simple returns for every start day in the lookback window ending at `idx`."""
    window = prices.iloc[idx - params.lookback: idx + 1]
    rets = (window.shift(-params.horizon) / window - 1.0).dropna()   # last `horizon` rows drop out: no future data
    if params.stress_start and prices.index[idx] >= pd.Timestamp(params.stress_end):
        s = prices.loc[params.stress_start: params.stress_end]
        s_rets = (s.shift(-params.horizon) / s - 1.0).dropna()      # uses only prices up to stress_end <= today
        rets = pd.concat([rets, s_rets[~s_rets.index.isin(rets.index)]])
    return rets


def initial_margin(pos, prices, idx, params=PARAMS, use_concentration=True):
    """Return dict with IM, ES, number of scenarios, and the full loss vector."""
    date = prices.index[idx]
    spot = prices.iloc[idx]
    vol = trailing_vol(prices, idx, params.vol_window)
    tick = list(pos.ticker.unique())
    rets = scenario_returns(prices, idx, params)[tick]
    scales, weights = concentration_scales(pos, spot, params)
    if not use_concentration:
        scales = scales * 0 + 1.0
    S_scen = (1.0 + rets * scales[tick]) * spot[tick]
    base = portfolio_value(pos, spot[tick].to_frame().T.reset_index(drop=True), vol, date)[0]
    scen = portfolio_value(pos, S_scen.reset_index(drop=True), vol, date, shift=params.horizon / 252.0)
    losses = base - scen                                   # positive = client loses = bank's exposure grows
    var = max(float(np.quantile(losses, params.confidence)), 0.0)
    tail = losses[losses >= np.quantile(losses, params.confidence)]
    es = max(float(tail.mean()), 0.0)
    return dict(im=var, es=es, n_scen=len(losses), losses=losses, weights=weights, scales=scales)
