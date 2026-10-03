"""Synthetic clients and trades. EVERYTHING here is made up (fixed random seed) - no real client data.

Setup: each client trades with the bank through
  * SWAP trades: a total-return swap = the client is long the stock, the bank is the counterparty.
  * PUT trades:  the client WRITES (sells) put options to the bank, i.e. qty < 0. If stocks fall the client owes the bank.
Value to the client moves with the stock; when it goes negative the client owes the bank money.
"""
import numpy as np
import pandas as pd
from .bs import bs_price
from .config import SEED, RISK_FREE_RATE
from .valuation import trailing_vol

CLIENTS = pd.DataFrame([
    dict(client_id="A", name="Diversified Long Equity Fund", collateral_pct=0.10, exposure_limit=3_000_000),
    dict(client_id="B", name="Concentrated Single-Stock Fund", collateral_pct=0.10, exposure_limit=2_000_000),
    dict(client_id="C", name="Mixed Equity & Options Fund", collateral_pct=0.10, exposure_limit=2_500_000),
])

# (client, ticker, instrument, target notional in USD)
BOOK = (
    [("A", t, "SWAP", 10e6) for t in ["AAPL", "MSFT", "JNJ", "PG", "KO", "JPM", "WMT", "HD", "V", "XOM"]]
    + [("B", "TSLA", "SWAP", 40e6), ("B", "NVDA", "SWAP", 8e6), ("B", "META", "SWAP", 6e6), ("B", "AMZN", "SWAP", 6e6)]
    + [("C", t, "SWAP", 10e6) for t in ["GOOGL", "BAC", "CVX", "MA", "ABBV"]]
    + [("C", t, "PUT", 10e6) for t in ["NVDA", "AMZN", "META"]]
)


def generate_trades(prices, asof_idx, seed=SEED):
    """Create the synthetic trade book as of row `asof_idx`. Returns (trades, clients)."""
    rng = np.random.default_rng(seed)
    asof = prices.index[asof_idx]
    rows = []
    for cid, tkr, inst, notional in BOOK:
        back = int(rng.integers(20, 120))                 # entered 20-120 trading days ago
        e_idx = asof_idx - back
        entry_date = prices.index[e_idx]
        s_entry = float(prices[tkr].iloc[e_idx])
        if inst == "SWAP":
            qty = round(notional / float(prices[tkr].iloc[asof_idx]) / 100) * 100
            rows.append(dict(client_id=cid, ticker=tkr, instrument="SWAP", qty=float(qty), strike=np.nan,
                             expiry=pd.NaT, entry_date=entry_date, entry_value=s_entry))
        else:
            strike = round(float(rng.uniform(0.88, 0.95)) * s_entry, 0)
            expiry = asof + pd.Timedelta(days=int(rng.integers(60, 150)))
            qty = -round(notional / strike / 100) * 100   # negative = client wrote (sold) the puts
            vol_e = trailing_vol(prices, e_idx)[tkr]
            T0 = (expiry - entry_date).days / 365.0
            premium = float(bs_price(s_entry, strike, T0, RISK_FREE_RATE, vol_e, "put"))
            rows.append(dict(client_id=cid, ticker=tkr, instrument="PUT", qty=float(qty), strike=strike,
                             expiry=expiry, entry_date=entry_date, entry_value=premium))
    trades = pd.DataFrame(rows)
    # collateral = flat % of gross notional at the as-of date (the bank's "rule of thumb" before the model)
    spot = prices.iloc[asof_idx]
    notional = trades.assign(n=lambda d: np.where(d.instrument == "SWAP", d.qty.abs() * d.ticker.map(spot),
                                                  d.qty.abs() * d.strike)).groupby("client_id")["n"].sum()
    clients = CLIENTS.copy()
    clients["gross_notional"] = clients.client_id.map(notional)
    clients["collateral"] = (clients.gross_notional * clients.collateral_pct).round(0)
    return trades, clients
