"""

    python main.py build-db <path-to-old-backtester-db>   copy prices into data/market_data.db
    python main.py fetch                                  refresh prices from Yahoo (needs internet)
    python main.py run                                    as-of exposure, margin, margin calls (printed + CSV)
    python main.py backtest                               margin-model backtest + charts + CSV
    python main.py sensitivity                            lookback / stressed-calibration comparison
    python main.py report                                 Excel report (needs `run` + `backtest` first)
    python main.py all                                    run, backtest, report, sensitivity
"""
import argparse
import dataclasses
import json
import sys

import pandas as pd

from risk_engine.backtest import book_from_trades, kupiec_pof, run_backtest, summarise
from risk_engine.clients import generate_trades
from risk_engine.config import FIG_DIR, OUT_DIR, PARAMS
from risk_engine.data import build_market_db, load_prices
from risk_engine.exposure import current_exposure, margin_call, mark_to_market, potential_exposure
from risk_engine.margin import initial_margin
from risk_engine.report import build_workbook, plot_backtest


def setup():
    OUT_DIR.mkdir(exist_ok=True)
    FIG_DIR.mkdir(exist_ok=True)
    prices = load_prices()
    idx = len(prices) - 1
    trades, clients = generate_trades(prices, idx)
    return prices, idx, trades, clients


def cmd_run():
    prices, idx, trades, clients = setup()
    rows, margins = [], {}
    for cl in clients.itertuples():
        pos = trades[trades.client_id == cl.client_id].reset_index(drop=True)
        m = mark_to_market(pos, prices, idx)
        res = initial_margin(pos, prices, idx)
        margins[cl.client_id] = res
        mtm, coll = float(m.mtm.sum()), float(cl.collateral)
        rows.append(dict(client=cl.client_id, name=cl.name, gross_notional=cl.gross_notional, mtm=mtm, collateral=coll,
                         exposure=current_exposure(mtm, coll), initial_margin=res["im"], expected_shortfall=res["es"],
                         margin_call=margin_call(res["im"], coll),
                         potential_exposure=potential_exposure(mtm, coll, res["im"]), limit=cl.exposure_limit,
                         top_name_weight=float(res["weights"].max()), scenarios=res["n_scen"]))
    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "exposure_summary.csv", index=False)
    pd.set_option("display.float_format", lambda x: f"{x:,.0f}" if abs(x) > 5 else f"{x:.2f}")
    print(f"As of {prices.index[idx]:%Y-%m-%d}\n", df.drop(columns=["name"]).to_string(index=False))
    return prices, idx, trades, clients, margins


def cmd_backtest(prices=None, idx=None, trades=None, clients=None):
    if prices is None:
        prices, idx, trades, clients = setup()
    summaries = {}
    for cl in clients.itertuples():
        pos = trades[trades.client_id == cl.client_id].reset_index(drop=True)
        book = book_from_trades(mark_to_market(pos, prices, idx))
        bt = run_backtest(book, prices)
        bt.to_csv(OUT_DIR / f"backtest_client_{cl.client_id}.csv")
        plot_backtest(cl.client_id, cl.name, bt, FIG_DIR / f"backtest_client_{cl.client_id}.png")
        s = summarise(bt)
        summaries[cl.client_id] = s
        d, n = s["daily_overlapping"], s["non_overlapping"]
        print(f"Client {cl.client_id}: daily {d['exceptions']}/{d['n']} = {d['rate']:.2%} | "
              f"independent {n['exceptions']}/{n['n']} = {n['rate']:.2%} (Kupiec p={n['kupiec_p']:.3f})")
    serial = {k: {kk: (vv.to_dict() if hasattr(vv, "to_dict") else vv) for kk, vv in v.items()} for k, v in summaries.items()}
    (OUT_DIR / "backtest_summary.json").write_text(json.dumps(serial, indent=2, default=float))
    return summaries


def cmd_sensitivity(prices=None, idx=None, trades=None, clients=None):
    if prices is None:
        prices, idx, trades, clients = setup()
    variants = {
        "base: 2y lookback": PARAMS,
        "3y lookback": dataclasses.replace(PARAMS, lookback=756),
        "2y + stressed 2020 window": dataclasses.replace(PARAMS, stress_start="2020-02-19", stress_end="2020-06-30"),
    }
    rows = []
    for cl in clients.itertuples():
        pos = trades[trades.client_id == cl.client_id].reset_index(drop=True)
        book = book_from_trades(mark_to_market(pos, prices, idx))
        for name, pr in variants.items():
            bt = run_backtest(book, prices, pr, start_date="2020-07-01")   # same test window for every variant
            ind = bt.iloc[::10]
            _, pv = kupiec_pof(len(ind), int(ind.exception.sum()))
            rows.append(dict(client=cl.client_id, variant=name, test_days=len(bt), exceptions=int(bt.exception.sum()),
                             exception_rate=bt.exception.mean(), avg_margin=bt.margin.mean(),
                             independent_exceptions=int(ind.exception.sum()), independent_n=len(ind), kupiec_p=pv))
    df = pd.DataFrame(rows)
    df["margin_vs_base"] = df.avg_margin / df.groupby("client").avg_margin.transform("first") - 1
    df.to_csv(OUT_DIR / "sensitivity.csv", index=False)
    print(df.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))


def cmd_report(prices, idx, trades, clients, margins, summaries):
    asof = prices.index[idx]
    path = OUT_DIR / f"exposure_report_{asof:%Y%m%d}.xlsx"
    build_workbook(path, asof, clients, trades, prices, idx, margins, summaries)
    print("Wrote", path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build-db", "fetch", "run", "backtest", "sensitivity", "report", "all"])
    ap.add_argument("src", nargs="?", help="source DB for build-db")
    a = ap.parse_args()
    if a.command == "build-db":
        print(build_market_db(a.src), "rows in data/market_data.db")
    elif a.command == "fetch":
        from risk_engine.fetch import fetch_prices
        from risk_engine.config import DB_PATH
        tickers = sorted(load_prices(DB_PATH).columns)
        print(fetch_prices(tickers), "rows upserted")
    elif a.command == "run":
        cmd_run()
    elif a.command == "backtest":
        cmd_backtest()
    elif a.command == "sensitivity":
        cmd_sensitivity()
    elif a.command == "report":
        prices, idx, trades, clients, margins = cmd_run()
        raw = json.loads((OUT_DIR / "backtest_summary.json").read_text())
        cmd_report(prices, idx, trades, clients, margins, raw)
    else:
        prices, idx, trades, clients, margins = cmd_run()
        summaries = cmd_backtest(prices, idx, trades, clients)
        cmd_report(prices, idx, trades, clients, margins, summaries)
        cmd_sensitivity(prices, idx, trades, clients)


if __name__ == "__main__":
    sys.exit(main())
