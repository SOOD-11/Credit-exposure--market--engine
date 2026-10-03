"""All tunable assumptions live here, so every number in the report can be traced to a setting."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "market_data.db"
OUT_DIR = ROOT / "outputs"
FIG_DIR = OUT_DIR / "figures"

SEED = 42                  # makes the synthetic clients reproducible
RISK_FREE_RATE = 0.04      # flat, annual. ASSUMPTION (not looked up); option prices are not very sensitive to it.
TRADING_DAYS = 252


@dataclass(frozen=True)
class MarginParams:
    confidence: float = 0.99       # margin = 99th percentile loss
    horizon: int = 10              # margin period of risk: trading days to close out a defaulted client
    lookback: int = 504            # ~2 years of history used to build scenarios
    vol_window: int = 252          # trailing window for option volatility
    conc_threshold: float = 0.25   # a single name above 25% of gross notional counts as "concentrated"
    conc_scale: float = 1.5 ** 0.5 # concentrated names take 50% longer to unwind -> sqrt(1.5) bigger moves
    # Optional "stressed calibration": once this window is in the past, its scenarios are added to the sample.
    stress_start: str = ""         # e.g. "2020-02-19" (empty = off)
    stress_end: str = ""           # e.g. "2020-06-30"


PARAMS = MarginParams()

# Constant-notional replay used by the model backtest (see backtest.py)
BACKTEST_OPTION_MONEYNESS = 0.92   # written puts struck at 92% of spot
BACKTEST_OPTION_TENOR = 0.40       # years to expiry, held constant
