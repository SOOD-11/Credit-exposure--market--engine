# Counterparty Exposure & Initial Margin Engine

A small, end-to-end version of what a bank's **credit risk exposure / collateral** team does:
value a client's portfolio, work out how much the client could owe the bank, decide how much
collateral (**initial margin**) to demand, issue margin calls, and **test whether the margin model would have been enough**.

> **All clients and trades are synthetic** (fixed random seed). Market prices are real daily closes for 20 US large caps, 2015-2025.
> This is a learning project, not a production model.

## The real-world problem
A bank trades with hedge funds and funds using swaps and options. If a client loses money and cannot pay,
the bank loses too (Archegos, 2021, is the textbook case). Banks hold **collateral** against that risk.
Too little collateral leaves the bank exposed; too much drives clients away. This project answers:
*"How much collateral should we hold against this client today, and was that number ever too low?"*

## What it does
1. **Data** - daily prices in SQLite (`data/market_data.db`, 55,300 rows, idempotent upserts).
2. **Synthetic book** - 3 clients: A diversified long-equity fund; B concentrated fund (TSLA = 67% of gross); C equity swaps plus **written puts**.
3. **Valuation** - equity swaps at market; options with Black-Scholes (price, delta, gamma, vega).
4. **Exposure** - `max(-MTM - collateral, 0)`: what the client owes beyond the collateral held.
5. **Initial margin** - historical simulation: replay every overlapping 10-day move of the last 2 years on *today's* portfolio (options fully repriced, time decay included); margin = 99th-percentile loss; also Expected Shortfall.
   Names above 25% of gross notional get scenario moves scaled by sqrt(1.5) (longer close-out for concentrated positions).
6. **Margin calls and limits** - call = `max(IM - collateral, 0)`; limit tested on *potential exposure* = `max(-(MTM - IM) - collateral, 0)`.
7. **Model backtest** - for every day 2017-2025, margin computed using only past data vs. the real next-10-day loss; exceptions counted and tested with **Kupiec's proportion-of-failures test**.
8. **Report** - Excel workbook with live formulas, per-client sheets, Greeks, backtest and assumptions sheets, and an auto-written commentary per client; plus a VBA macro that highlights breaches.

## Results (as of 30 Dec 2025)
| Client | Gross notional | Collateral (flat 10%) | Initial margin (99%, 10d) | Expected shortfall | Margin call | Potential exposure vs limit |
|---|---|---|---|---|---|---|
| A Diversified | $100.0m | $10.0m | $5.64m | $7.25m | none | $0 vs $3.0m - OK |
| B Concentrated | $60.0m | $6.0m | $13.24m | $15.35m | **$7.25m** | $4.71m vs $2.0m - **BREACH** |
| C Mixed + puts | $80.0m | $8.0m | $5.58m | $8.40m | none | $0 vs $2.5m - OK |

A flat 10% rule is fine for the diversified client but leaves the concentrated one badly under-collateralised.
(All three clients are currently in the money, so current uncovered exposure is $0; the risk is *forward-looking*.)

## Model backtest (Jan 2017 - Dec 2025, 2,250 test days, 99% confidence -> 1% expected)
| Client | Exceptions, every day | Exceptions, every 10th day (independent) | Kupiec p-value (independent) |
|---|---|---|---|
| A | 61 (2.71%) | 5 of 225 (2.22%) | 0.112 |
| B | 21 (0.93%) | 1 of 225 (0.44%) | 0.347 |
| C | 73 (3.24%) | 6 of 225 (2.67%) | **0.037 (rejected at 5%)** |

* Daily tests use overlapping windows, so exceptions cluster and the daily Kupiec p-values are overstated; the every-10th-day sample is the cleaner test.
* **Exceptions cluster in stress episodes** (2018, 2020, 2022, 2025; none in other years). See `outputs/figures/`.
  Cause: a 2-year window forgets old crises. Margin stays high for two years after 2020, then falls in early 2022 just before the 2022 sell-off (**procyclicality**).
* **The concentration add-on matters:** for client B the same backtest *without* it gives 47 exceptions (2.09%) vs 21 (0.93%) with it.
  Without the add-on, B's margin today would be $11.21m instead of $13.24m.

## Recalibration experiment (test window Jul 2020 - Dec 2025, 1,372 days, same for every variant)
| Client | Variant | Exceptions (daily) | Rate | Average margin vs base |
|---|---|---|---|---|
| A | base 2-year lookback | 24 | 1.75% | - |
| A | 3-year lookback | 2 | 0.15% | +4.8% |
| A | 2-year + stressed 2020 window | 0 | 0.00% | +58.7% |
| B | base | 8 | 0.58% | - |
| B | 3-year lookback | 4 | 0.29% | -3.3% |
| B | 2-year + stressed 2020 window | 2 | 0.15% | +16.3% |
| C | base | 31 | 2.26% | - |
| C | 3-year lookback | 5 | 0.36% | +5.7% |
| C | 2-year + stressed 2020 window | 0 | 0.00% | +56.3% |

A 3-year lookback removes most exceptions for little extra margin; pooling the 2020 crash is safer but costs ~57% more collateral
(the "commercially viable" trade-off). This window contains only a few independent stress episodes, so treat it as indicative, not proof.
The 3-year setting is **not** the default in `config.py` (default = 2 years).

## How to run
```bash
pip install -r requirements.txt
python main.py run          # exposure, margin, margin calls
python main.py backtest     # model backtest + charts (about 90 seconds)
python main.py report       # Excel report (run `backtest` first)
python main.py sensitivity  # recalibration table (about 3 minutes)
python main.py all          # everything
pytest -q                   # 8 tests
```
Outputs land in `outputs/` (CSV, JSON, PNG charts, Excel).
To use the VBA macro: open the report, press Alt+F11, File > Import File > `reports/margin_macro.bas`, run `HighlightBreaches`.

## Tests (8, all passing)
Put-call parity; Greeks vs finite differences; expired option = intrinsic value; exposure / margin-call / potential-exposure logic;
margin on a hand-checkable single-stock portfolio; **no look-ahead** (changing future prices does not change today's margin);
concentration flagging; Kupiec test against closed-form values.

## Assumptions and limitations
* Synthetic clients and trades; flat 10% collateral as the "rule of thumb" benchmark; one netting set per client.
* Instruments: equity swaps and written European puts only. No FX, rates, CDS (the data has equities only), no dividends.
* Risk-free rate fixed at 4% (assumption). Option volatility = trailing 252-day realised vol, held constant in scenarios (no vega risk in the margin).
* The backtest replays portfolios of the same *shape* as today's (constant dollar notionals, puts re-struck at 92% moneyness / 0.4y tenor),
  because historical positions are not available.
* Past moves are assumed to describe future moves; ~495 scenarios means the 99th percentile rests on about 5 observations.
* Not tested here: `risk_engine/fetch.py` (needs internet) and the VBA macro (needs Excel). Run both once on your machine before relying on them.
* Prices come from an earlier yfinance download; the closes appear to be dividend-adjusted.
