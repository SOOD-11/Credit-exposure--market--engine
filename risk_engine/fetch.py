"""Optional: refresh prices from Yahoo Finance (needs internet; run `python main.py fetch`)."""
import sqlite3
import yfinance as yf
from .config import DB_PATH


def fetch_prices(tickers, start="2015-01-01", db_path=DB_PATH):
    raw = yf.download(tickers, start=start, auto_adjust=True, progress=False)["Close"]
    long = raw.stack().reset_index()
    long.columns = ["date", "ticker", "close"]
    long["date"] = long["date"].dt.strftime("%Y-%m-%d")
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE IF NOT EXISTS prices (date TEXT, ticker TEXT, close REAL, PRIMARY KEY (date, ticker))")
    con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?)", long.itertuples(index=False, name=None))
    con.commit()
    con.close()
    return len(long)
