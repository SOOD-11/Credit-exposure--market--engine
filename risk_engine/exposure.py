"""Mark-to-market, credit exposure and margin calls."""
import numpy as np
import pandas as pd
from .valuation import trailing_vol, unit_values


def mark_to_market(pos, prices, idx):
    """Per-position MTM to the client: qty * (current unit value - entry value)."""
    date, spot = prices.index[idx], prices.iloc[idx]
    vol = trailing_vol(prices, idx)
    uv = unit_values(pos, spot.to_frame().T.reset_index(drop=True), vol, date)[0]
    out = pos.copy()
    out["spot"] = out.ticker.map(spot)
    out["unit_value"] = uv
    out["mtm"] = out.qty * (out.unit_value - out.entry_value)
    out["notional"] = np.where(out.instrument == "SWAP", out.qty.abs() * out.spot, out.qty.abs() * out.strike)
    return out


def current_exposure(total_mtm, collateral):
    """Bank's uncovered credit exposure: what the client owes (negative MTM) minus collateral held, floored at 0."""
    return max(-total_mtm - collateral, 0.0)


def margin_call(initial_margin, collateral):
    """Extra collateral to request so that collateral covers the model initial margin."""
    return max(initial_margin - collateral, 0.0)


def potential_exposure(total_mtm, collateral, initial_margin):
    """Exposure if the client then suffers a 99% / 10-day loss (= the margin amount) and has not paid:
    max(-(MTM - IM) - collateral, 0). Exposure limits are checked against this forward-looking number."""
    return max(-(total_mtm - initial_margin) - collateral, 0.0)
