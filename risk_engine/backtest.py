"""Backtest of the initial-margin model.

For every historical date t (after 2 years of warm-up) we
  1. build a client portfolio of the same SHAPE as today's (same names, same $ notionals, options re-struck at
     a constant moneyness/tenor), because real positions change over time and we only hold today's book,
  2. compute the margin IM_t using ONLY data up to t,
  3. measure the REAL loss of that portfolio over the next 10 trading days,
  4. record an "exception" when the real loss is bigger than IM_t.
A 99% model should have exceptions on about 1% of days. Kupiec's test checks whether the count is consistent with 1%.
"""
import numpy as np
import pandas as pd
from scipy.stats import chi2
from .config import PARAMS, BACKTEST_OPTION_MONEYNESS, BACKTEST_OPTION_TENOR
from .margin import initial_margin
from .valuation import trailing_vol, portfolio_value


def portfolio_at(book, prices, idx):
    """Re-create a client's book at row `idx`: constant $ notionals, puts at fixed moneyness/tenor."""
    date, spot = prices.index[idx], prices.iloc[idx]
    rows = []
    for b in book.itertuples():
        if b.instrument == "SWAP":
            rows.append(dict(ticker=b.ticker, instrument="SWAP", qty=b.notional / spot[b.ticker], strike=np.nan, expiry=pd.NaT))
        else:
            k = BACKTEST_OPTION_MONEYNESS * spot[b.ticker]
            rows.append(dict(ticker=b.ticker, instrument="PUT", qty=-b.notional / k, strike=k,
                             expiry=date + pd.Timedelta(days=int(BACKTEST_OPTION_TENOR * 365))))
    return pd.DataFrame(rows)


def book_from_trades(pos_mtm):
    """Collapse a client's current positions into (ticker, instrument, notional) rows."""
    return pos_mtm[["ticker", "instrument", "notional"]].reset_index(drop=True)


def kupiec_pof(n, x, p=0.01):
    """Kupiec proportion-of-failures likelihood-ratio test. Returns (LR statistic, p-value)."""
    if n == 0:
        return np.nan, np.nan
    ll0 = (n - x) * np.log(1 - p) + x * np.log(p)
    phat = x / n
    ll1 = 0.0 if x in (0, n) else (n - x) * np.log(1 - phat) + x * np.log(phat)
    lr = -2.0 * (ll0 - ll1)
    return float(lr), float(1 - chi2.cdf(lr, df=1))


def run_backtest(book, prices, params=PARAMS, use_concentration=True, start_date=None, step=1):
    """Return a DataFrame indexed by test date with margin, realised loss and exception flag."""
    h = params.horizon
    start = max(params.lookback, params.vol_window) + 1
    recs = []
    if start_date is not None:
        start = max(start, int(prices.index.searchsorted(pd.Timestamp(start_date))))
    for idx in range(start, len(prices) - h, step):
        pos = portfolio_at(book, prices, idx)
        res = initial_margin(pos, prices, idx, params, use_concentration)
        date, spot0 = prices.index[idx], prices.iloc[idx]
        tick = list(pos.ticker.unique())
        vol0 = trailing_vol(prices, idx, params.vol_window)
        v0 = portfolio_value(pos, spot0[tick].to_frame().T.reset_index(drop=True), vol0, date)[0]
        vol1 = trailing_vol(prices, idx + h, params.vol_window)      # realised world: vol may have changed
        v1 = portfolio_value(pos, prices.iloc[idx + h][tick].to_frame().T.reset_index(drop=True), vol1, date,
                             shift=h / 252.0)[0]
        recs.append((date, res["im"], res["es"], v0 - v1))
    bt = pd.DataFrame(recs, columns=["date", "margin", "es", "realised_loss"]).set_index("date")
    bt["exception"] = bt.realised_loss > bt.margin
    return bt


def summarise(bt, params=PARAMS):
    """Exception statistics: every day (overlapping windows) and every 10th day (non-overlapping)."""
    p = 1 - params.confidence
    out = {}
    for label, sub in [("daily_overlapping", bt), ("non_overlapping", bt.iloc[:: params.horizon])]:
        n, x = len(sub), int(sub.exception.sum())
        lr, pv = kupiec_pof(n, x, p)
        out[label] = dict(n=n, exceptions=x, rate=x / n, expected_rate=p, kupiec_lr=lr, kupiec_p=pv)
    by_year = bt.groupby(bt.index.year).exception.agg(["sum", "count"])
    out["by_year"] = by_year
    return out
