"""
Fetches historical daily price data (US and European tickers both work
through yfinance, since it pulls straight from Yahoo Finance) and stores
it in the local SQLite database.
"""
import time
import datetime as dt
from typing import Iterable, Optional

import pandas as pd
import yfinance as yf

from database import get_session, Stock, PriceBar, init_db
from tickers import get_universe, EU_BLUE_CHIPS, get_exchange_tickers, list_exchanges, load_tickers_from_csv


def _infer_market(symbol: str) -> str:
    """Guess market from ticker suffix. No suffix (or .US) => US."""
    eu_suffixes = (".L", ".DE", ".PA", ".AS", ".MI", ".SW", ".MC", ".ST",
                   ".BR", ".OL", ".CO", ".HE", ".LS", ".VI", ".IR")
    return "EU" if symbol.endswith(eu_suffixes) else "US"


def upsert_stock(session, symbol: str, name: str = "", exchange: str = "",
                  currency: str = "", sector: str = "", market: Optional[str] = None) -> Stock:
    stock = session.query(Stock).filter_by(symbol=symbol).one_or_none()
    if stock is None:
        stock = Stock(
            symbol=symbol,
            name=name or symbol,
            market=market or _infer_market(symbol),
            exchange=exchange,
            currency=currency,
            sector=sector,
        )
        session.add(stock)
        session.commit()
    return stock


def fetch_and_store(symbols: Iterable[str], start: str = "2015-01-01",
                     end: Optional[str] = None, pause: float = 0.3,
                     meta: Optional[dict] = None, progress_cb=None) -> dict:
    """
    Downloads daily OHLCV data for each symbol and upserts it into the DB.

    symbols  : iterable of yfinance tickers, e.g. ["AAPL", "SAP.DE"]
    start/end: 'YYYY-MM-DD' date strings (end defaults to today)
    meta     : optional dict {symbol: (name, exchange, currency, sector)}
    progress_cb: optional callable(symbol, i, total, status) for CLI progress

    Returns a summary dict {symbol: num_rows_upserted or 'ERROR: ...'}
    """
    init_db()
    session = get_session()
    meta = meta or {}
    end = end or dt.date.today().isoformat()
    symbols = list(symbols)
    summary = {}

    try:
        for i, symbol in enumerate(symbols, start=1):
            try:
                name, exchange, currency, sector = meta.get(symbol, ("", "", "", ""))
                stock = upsert_stock(session, symbol, name, exchange, currency, sector)

                df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
                if df is None or df.empty:
                    summary[symbol] = "ERROR: no data returned"
                    if progress_cb:
                        progress_cb(symbol, i, len(symbols), "no data")
                    continue

                # yfinance sometimes returns MultiIndex columns for a single ticker
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                df = df.reset_index()
                rows_upserted = 0
                existing_dates = {
                    d for (d,) in session.query(PriceBar.date).filter_by(stock_id=stock.id).all()
                }

                for _, row in df.iterrows():
                    bar_date = row["Date"].date() if hasattr(row["Date"], "date") else row["Date"]
                    if bar_date in existing_dates:
                        continue
                    bar = PriceBar(
                        stock_id=stock.id,
                        date=bar_date,
                        open=float(row["Open"]) if pd.notna(row["Open"]) else None,
                        high=float(row["High"]) if pd.notna(row["High"]) else None,
                        low=float(row["Low"]) if pd.notna(row["Low"]) else None,
                        close=float(row["Close"]) if pd.notna(row["Close"]) else None,
                        adj_close=float(row["Adj Close"]) if "Adj Close" in row and pd.notna(row["Adj Close"]) else float(row["Close"]),
                        volume=float(row["Volume"]) if pd.notna(row["Volume"]) else None,
                    )
                    session.add(bar)
                    rows_upserted += 1

                session.commit()
                summary[symbol] = rows_upserted
                if progress_cb:
                    progress_cb(symbol, i, len(symbols), f"{rows_upserted} new rows")
            except Exception as exc:
                session.rollback()
                summary[symbol] = f"ERROR: {exc}"
                if progress_cb:
                    progress_cb(symbol, i, len(symbols), f"error: {exc}")
            time.sleep(pause)  # be polite to Yahoo Finance
    finally:
        session.close()

    return summary


def fetch_universe(market: str = "ALL", start: str = "2015-01-01",
                    end: Optional[str] = None, limit: Optional[int] = None,
                    progress_cb=None) -> dict:
    """
    Fetches a whole preset universe ('US', 'EU', or 'ALL') and stores it.
    `limit` caps the number of tickers (useful for quick tests).
    """
    universe = get_universe(market)
    symbols = list(universe.keys())
    if limit:
        symbols = symbols[:limit]
    return fetch_and_store(symbols, start=start, end=end, meta=universe, progress_cb=progress_cb)


def fetch_exchange(exchange_code: str, start: str = "2015-01-01",
                    end: Optional[str] = None, limit: Optional[int] = None,
                    progress_cb=None) -> dict:
    """
    Fetches every ticker in one curated exchange list, e.g.:
        fetch_exchange("NASDAQ_HELSINKI", start="2015-01-01")
    See tickers.list_exchanges() for all available exchange codes.
    """
    universe = get_exchange_tickers(exchange_code)
    symbols = list(universe.keys())
    if limit:
        symbols = symbols[:limit]
    return fetch_and_store(symbols, start=start, end=end, meta=universe, progress_cb=progress_cb)


def fetch_from_csv(csv_path: str, start: str = "2015-01-01", end: Optional[str] = None,
                    default_market: str = "EU", default_exchange: str = "",
                    default_currency: str = "", limit: Optional[int] = None,
                    progress_cb=None) -> dict:
    """
    Fetches every ticker listed in a CSV file (for a fully complete/custom
    exchange listing beyond the curated dicts in tickers.py). See
    tickers.load_tickers_from_csv() for the expected CSV format.
    """
    universe = load_tickers_from_csv(csv_path, default_market=default_market,
                                      default_exchange=default_exchange,
                                      default_currency=default_currency)
    symbols = list(universe.keys())
    if limit:
        symbols = symbols[:limit]
    return fetch_and_store(symbols, start=start, end=end, meta=universe, progress_cb=progress_cb)
