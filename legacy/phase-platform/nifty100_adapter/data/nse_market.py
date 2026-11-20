"""Load the current Nifty 100 universe and published NSE end-of-day data."""

from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
import io
import math
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

ARCHIVES = "https://nsearchives.nseindia.com"
UNIVERSE_URL = ARCHIVES + "/content/indices/ind_nifty100list.csv"
MARKET_TIME = timezone(timedelta(hours=5, minutes=30))
MISSING_CHECKS = ["ASM/GSM surveillance", "promoter pledging", "legal cases", "regulatory actions"]


def download(url, limit):
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("NSE returned an unexpectedly large data file.")
    return data


def read_rows(data, columns):
    rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if not set(columns).issubset(rows.fieldnames or ()):
        raise ValueError("NSE returned an unexpected data format.")
    return rows


def equity_session(day, instruments):
    filename = f"BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv"
    try:
        archive = download(f"{ARCHIVES}/content/cm/{filename}.zip", 5_000_000)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    try:
        with ZipFile(io.BytesIO(archive)) as bundle:
            if bundle.getinfo(filename).file_size > 8_000_000:
                raise ValueError("NSE returned an unexpectedly large report.")
            content = bundle.read(filename)
    except (BadZipFile, KeyError):
        raise ValueError("NSE returned an unreadable bhavcopy archive.") from None

    columns = ("TradDt", "ISIN", "TckrSymb", "SctySrs", "ClsPric", "TtlTrfVal")
    prices = {}
    for row in read_rows(content, columns):
        key = (row["ISIN"], row["TckrSymb"], row["SctySrs"])
        if row["TradDt"] != day.isoformat() or key not in instruments:
            continue
        try:
            close = float(row["ClsPric"])
            turnover = float(row["TtlTrfVal"])
        except (ValueError, TypeError):
            continue
        if math.isfinite(close) and close > 0 and math.isfinite(turnover) and turnover >= 0:
            prices[key] = close, turnover
    if not prices:
        raise ValueError(f"NSE bhavcopy {day} contained no usable Nifty 100 prices.")
    return prices


def load_nifty100(today=None):
    """Return a market snapshot and provenance for a paper-only strategy."""
    import pandas as pd

    today = today or datetime.now(MARKET_TIME).date()
    try:
        rows = read_rows(download(UNIVERSE_URL, 200_000), ("ISIN Code", "Symbol", "Series", "Company Name", "Industry"))
        members = list(rows)
        industries = {row["Symbol"]: row["Industry"] for row in members}
        instruments = {
            (row["ISIN Code"], row["Symbol"], row["Series"]): row["Company Name"]
            for row in members
        }
        if len(instruments) != 100 or len({key[1] for key in instruments}) != 100:
            raise ValueError("The NSE constituent file did not contain 100 distinct stocks.")
        days = [today - timedelta(days=offset) for offset in range(18)]
        sessions = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            for offset in range(0, len(days), 6):
                batch = days[offset:offset + 6]
                reports = executor.map(lambda day: equity_session(day, instruments), batch)
                sessions.extend((day, data) for day, data in zip(batch, reports) if data is not None)
                if len(sessions) >= 6:
                    break
    except OSError:
        raise ValueError("Could not retrieve NSE market data. Try again shortly.") from None

    if len(sessions) < 6 or (today - sessions[0][0]).days > 7:
        raise ValueError("NSE has not returned enough recent sessions to calculate five-session momentum.")
    latest_day, latest = sessions[0]
    base_day, baseline = sessions[5]
    previous = sessions[1][1]
    snapshot = []
    for key in latest.keys() & baseline.keys():
        close, turnover = latest[key]
        momentum = (close / baseline[key][0] - 1) * 100
        snapshot.append({
            "symbol": key[1],
            "isin": key[0],
            "industry": industries[key[1]],
            "company_name": instruments[key],
            "close": close,
            "daily_turnover_crore": turnover / 10_000_000,
            "price_momentum_weekly": momentum,
            "price_momentum_daily": (close / previous[key][0] - 1) * 100 if key in previous else None,
        })
    if not snapshot:
        raise ValueError("The NSE reports contained no matching Nifty 100 prices across both sessions.")
    frame = pd.DataFrame(snapshot).sort_values("symbol")
    return frame, {
        "source": "NSE cash-market bhavcopy",
        "asOf": latest_day.isoformat(),
        "comparisonDate": base_day.isoformat(),
        "universeSize": len(instruments),
        "covered": len(frame),
        "unverifiedChecks": MISSING_CHECKS,
    }
