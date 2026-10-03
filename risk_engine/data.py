"""Market data access. Prices live in SQLite (table `prices`, primary key (date, ticker))."""
import sqlite3
import pandas as pd
from .config import DB_PATH


def build_market_db(src_db, dst_db=DB_PATH):
    """Copy daily closes from the earlier backtester database into this project's DB (idempotent)."""
    src = sqlite3.connect(src_db)
    df = pd.read_sql("SELECT Date AS date, ticker, Close AS close FROM prices", src)
    src.close()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    dst = sqlite3.connect(dst_db)
    dst.execute("CREATE TABLE IF NOT EXISTS prices (date TEXT, ticker TEXT, close REAL, PRIMARY KEY (date, ticker))")
    dst.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?)", df[["date", "ticker", "close"]].itertuples(index=False, name=None))
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    dst.close()
    return n


def load_prices(db_path=DB_PATH):
    """Wide DataFrame: index = trading date, columns = ticker, values = close."""
    con = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT date, ticker, close FROM prices", con, parse_dates=["date"])
    con.close()
    wide = df.pivot(index="date", columns="ticker", values="close").sort_index()
    if wide.isna().any().any():
        raise ValueError("Missing prices: fill or drop gaps before running the engine.")
    return wide
