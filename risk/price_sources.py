import csv
import datetime
import io
import logging
from decimal import Decimal, InvalidOperation

import requests

logger = logging.getLogger(__name__)

STOOQ_URL = "https://stooq.com/q/d/l/"


def fetch_from_stooq(ticker, start, end):
    """Daily closes for a US-listed ticker from Stooq's CSV export. Returns
    [] (never raises for a plain no-data response) so callers can fall
    back to yfinance."""
    symbol = f"{ticker.lower()}.us"
    params = {
        "s": symbol,
        "d1": start.strftime("%Y%m%d"),
        "d2": end.strftime("%Y%m%d"),
        "i": "d",
    }
    headers = {"User-Agent": "Mozilla/5.0 (compatible; risk-engine/1.0)"}
    response = requests.get(STOOQ_URL, params=params, headers=headers, timeout=10)
    response.raise_for_status()

    text = response.text.strip()
    if not text or text.startswith("No data"):
        return []

    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        try:
            price_date = datetime.datetime.strptime(row["Date"], "%Y-%m-%d").date()
            close = Decimal(row["Close"])
        except (KeyError, ValueError, InvalidOperation):
            continue
        rows.append((price_date, close))
    return rows


def fetch_from_yfinance(ticker, start, end):
    import yfinance as yf  # optional fallback dependency, imported lazily

    data = yf.download(ticker, start=start, end=end, progress=False)
    if data.columns.nlevels > 1:
        # yfinance returns MultiIndex columns (Price, Ticker) even for a
        # single symbol; drop the ticker level to get flat "Close" etc.
        data.columns = data.columns.droplevel(1)

    rows = []
    for index, row in data.iterrows():
        price_date = index.date() if hasattr(index, "date") else index
        try:
            # round first: yfinance's auto-adjusted close carries binary
            # float noise past 4-5 decimal places that isn't real precision.
            close = Decimal(str(round(float(row["Close"]), 4)))
        except (InvalidOperation, TypeError, ValueError):
            continue
        rows.append((price_date, close))
    return rows


def fetch_prices(ticker, start, end):
    """Stooq first, yfinance as fallback. Returns [] (not an exception) if
    both sources have nothing for this ticker/date range."""
    try:
        rows = fetch_from_stooq(ticker, start, end)
    except requests.RequestException as exc:
        logger.warning("Stooq fetch failed for %s: %s", ticker, exc)
        rows = []

    if rows:
        return rows

    logger.info("No Stooq data for %s; trying yfinance", ticker)
    try:
        return fetch_from_yfinance(ticker, start, end)
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", ticker, exc)
        return []
