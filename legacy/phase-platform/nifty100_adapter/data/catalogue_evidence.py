"""Collect typed, dated catalogue evidence without filling gaps with guesses."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit

from ..ai_parameters import PARAMETERS, availability
from .nse_market import ARCHIVES, MARKET_TIME, download, read_rows

API = "https://www.nseindia.com/api/"
SHAREHOLDING = "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"
ACTIONS = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
ANNOUNCEMENTS = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
DEALS = "https://www.nseindia.com/report-detail/display-bulk-and-block-deals"
PE_REPORT = "https://nsearchives.nseindia.com/content/circulars/CML66879.pdf"
LOOKBACK = {"daily": 0, "weekly": 8, "monthly": 35, "quarterly": 120, "yearly": 370,
            "annually": 370, "on-event": 30, "per_trade": 0, "fy_update": 370}


def finite(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def exchange_time(value):
    for shape in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime(value, shape).replace(tzinfo=MARKET_TIME)
        except (TypeError, ValueError):
            continue
    return None


def endpoint(name, start, end):
    query = urlencode({"index": "equities", "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y")})
    return f"{API}{name}?{query}"


def json_rows(url, required):
    payload = json.loads(download(url, 8_000_000))
    if not isinstance(payload, list) or any(not isinstance(row, dict) or not set(required).issubset(row) for row in payload):
        raise ValueError("Unexpected NSE corporate feed schema.")
    return payload


def observation(symbol, value, stamp, source):
    return {"symbol": symbol, "value": value, "asOf": stamp.isoformat(), "source": source}


def pe_data(members, day, cutoff):
    url = f"{ARCHIVES}/content/equities/peDetail/PE_{day:%d%m%y}.csv"
    rows = read_rows(download(url, 400_000), ("SYMBOL", "SYMBOL P/E"))
    pe = {}
    for row in rows:
        symbol = row["SYMBOL"].strip()
        value = finite(row["SYMBOL P/E"])
        if symbol in members and value is not None and value > 0:
            if symbol in pe:
                raise ValueError("The NSE P/E report returned a duplicate constituent.")
            pe[symbol] = value
    groups = defaultdict(list)
    for symbol, value in pe.items():
        groups[members[symbol].industry].append(value)
    from statistics import median

    values = []
    for symbol, value in pe.items():
        industry = members[symbol].industry
        peer_group = groups[industry]
        if len(peer_group) >= 3:
            reference = median(peer_group)
            values.append(observation(symbol, {
                "pe": value, "nifty100_industry": industry, "industry_median_pe": reference,
                "relative_pe": round(value / reference, 4), "peer_count": len(peer_group),
            }, day, url))
    return {"pe_ratio_vs_sector": values}


def ownership_data(members, day, cutoff):
    url = endpoint("corporate-share-holdings-master", day - timedelta(days=120), day)
    latest = {}
    for row in json_rows(url, ("symbol", "isin", "date", "broadcastDate", "pr_and_prgrp", "public_val")):
        symbol = row["symbol"]
        if symbol not in members or row["isin"] != members[symbol].isin:
            continue
        published, quarter = exchange_time(row["broadcastDate"]), exchange_time(row["date"])
        promoter, public = finite(row["pr_and_prgrp"]), finite(row["public_val"])
        if not (
            published and quarter and quarter <= published <= cutoff and (day - quarter.date()).days <= 140
            and promoter is not None and 0 <= promoter <= 100
            and public is not None and 0 <= public <= 100
        ):
            continue
        if symbol not in latest or (quarter, published) > latest[symbol][0]:
            latest[symbol] = ((quarter, published), observation(symbol, {
                "promoter_pct": promoter, "public_pct": public, "quarter_end": quarter.date().isoformat(),
            }, published, SHAREHOLDING))
    return {"promoter_holding_pct": [item[1] for item in latest.values()]}


def actions_data(members, day, cutoff):
    url = endpoint("corporates-corporateActions", day - timedelta(days=30), day)
    grouped = defaultdict(list)
    for row in json_rows(url, ("symbol", "isin", "exDate", "subject")):
        symbol = row["symbol"]
        ex_date = exchange_time(row["exDate"])
        subject = row["subject"]
        if (
            symbol in members and row["isin"] == members[symbol].isin and ex_date
            and day - timedelta(days=30) <= ex_date.date() <= day and isinstance(subject, str) and subject.strip()
        ):
            grouped[symbol].append({"ex_date": ex_date.date().isoformat(), "subject": subject.strip()[:200]})
    result = {"corporate_actions": [], "corporate_action_dividends": []}
    for symbol, events in grouped.items():
        events.sort(key=lambda item: item["ex_date"], reverse=True)
        result["corporate_actions"].append(observation(symbol, events[:10], day, ACTIONS))
        dividends = [event for event in events if re.search(r"\bdividend\b", event["subject"], re.I)]
        if dividends:
            result["corporate_action_dividends"].append(observation(symbol, dividends[:10], day, ACTIONS))
    return result


def announcements_data(members, day, cutoff):
    url = endpoint("corporate-announcements", day, day)
    latest = {}
    for row in json_rows(url, ("symbol", "sm_isin", "an_dt", "desc")):
        symbol = row["symbol"]
        stamp = exchange_time(row["an_dt"])
        title = row["desc"]
        if (symbol in members and row["sm_isin"] == members[symbol].isin and stamp
            and stamp.date() == day and stamp <= cutoff and isinstance(title, str) and title.strip()
            and (symbol not in latest or stamp.isoformat() > latest[symbol]["asOf"])):
            latest[symbol] = observation(symbol, {"exchange_category": title.strip()[:200]}, stamp, ANNOUNCEMENTS)
    return {"company_news": list(latest.values())}


def deals_data(members, day, cutoff):
    counts = defaultdict(lambda: {"bulk": 0, "block": 0})
    failures = []
    for kind in ("bulk", "block"):
        try:
            rows = read_rows(download(f"{ARCHIVES}/content/equities/{kind}.csv", 400_000), ("Date", "Symbol", "Quantity Traded"))
            for row in rows:
                trade_date = exchange_time(row["Date"])
                quantity = finite(row["Quantity Traded"])
                if trade_date and trade_date.date() == day and row["Symbol"] in members and quantity is not None and quantity > 0:
                    counts[row["Symbol"]][kind] += 1
        except (OSError, ValueError, KeyError, TypeError):
            failures.append(kind)
    if len(failures) == 2:
        raise ValueError("Neither NSE deal report could be read.")
    result = [observation(symbol, {kind: count for kind, count in totals.items() if count > 0}, day, DEALS)
              for symbol, totals in counts.items()]
    return {"bulk_block_deals": result}


BUILTIN = (
    (("pe_ratio_vs_sector",), pe_data, PE_REPORT),
    (("promoter_holding_pct",), ownership_data, SHAREHOLDING),
    (("corporate_actions", "corporate_action_dividends"), actions_data, ACTIONS),
    (("company_news",), announcements_data, ANNOUNCEMENTS),
    (("bulk_block_deals",), deals_data, DEALS),
)


def local_evidence(members, day, cutoff, path):
    with path.open("rb") as stream:
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Local feed evidence file is larger than 2 MB.")
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("Local evidence must contain a JSON array.")
    results = defaultdict(list)
    seen = set()
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Local evidence rows must be objects.")
        key, symbol, raw_date, url, value = (row.get(field) for field in ("parameter", "symbol", "asOf", "source", "value"))
        if not isinstance(key, str) or key not in PARAMETERS or not isinstance(symbol, str) or (symbol != "*" and symbol not in members):
            raise ValueError("Local evidence contains an unknown parameter or nonmember symbol.")
        if symbol == "*" and PARAMETERS[key].role_type.value in ("Score", "Filter", "Veto"):
            raise ValueError(f"{key} needs company-specific observations.")
        stamp = datetime.fromisoformat(raw_date) if isinstance(raw_date, str) else None
        if stamp is None or stamp.tzinfo is None or stamp > cutoff:
            raise ValueError("Local evidence requires an ISO timestamp with timezone, at or before the market cutoff.")
        uri = urlsplit(url) if isinstance(url, str) else None
        if not uri or uri.scheme != "https" or not uri.hostname or uri.username or uri.password:
            raise ValueError("Local feed evidence requires an HTTPS source link without credentials.")
        if type(value) not in (str, int, float, bool) or (isinstance(value, str) and not value.strip()) or (
            type(value) in (int, float) and finite(value) is None
        ):
            raise ValueError("Local evidence requires a nonblank scalar value.")
        if (key, symbol) in seen:
            raise ValueError("Local evidence contains duplicate parameter and symbol observations.")
        seen.add((key, symbol))
        stale = (day - stamp.astimezone(MARKET_TIME).date()).days > LOOKBACK[PARAMETERS[key].refresh_schedule]
        results[key].append({**observation(symbol, str(value)[:240] if isinstance(value, str) else value, stamp, url), "stale": stale})
    return results


def collect_evidence(frame, market, now=None):
    day = date.fromisoformat(market["asOf"])
    cutoff = min(now or datetime.now(MARKET_TIME), datetime.combine(day, time.max, tzinfo=MARKET_TIME))
    members = {row.symbol: row for row in frame.itertuples(index=False)}

    def fetch(spec):
        keys, loader, source = spec
        try:
            return {key: {"status": "Observed NSE evidence" if values else "No verified observations",
                          "source": source, "covered": len(values), "sample": values[:2]}
                    for key, values in loader(members, day, cutoff).items()}
        except (OSError, ValueError, KeyError, TypeError):
            return {key: {"status": "Feed error", "source": source, "covered": 0, "sample": []} for key in keys}

    with ThreadPoolExecutor(max_workers=4) as executor:
        observations = {key: item for result in executor.map(fetch, BUILTIN) for key, item in result.items()}
    error = ""
    local = {}
    path = os.environ.get("SI_TRADER_CATALOGUE_FEED")
    if path:
        try:
            local = local_evidence(members, day, cutoff, Path(path))
        except (OSError, ValueError, TypeError) as exc:
            error = f"Local evidence file was rejected: {exc}"
    rows = []
    for key, parameter in PARAMETERS.items():
        status = availability(key)
        effective = observations.get(key, {"status": status, "covered": market["covered"] if status == "NSE data" else 0, "sample": []})
        imported = local.get(key, [])
        fresh = [item for item in imported if not item["stale"]]
        rows.append({
            "key": key, "label": parameter.display_name, "role": parameter.role_type.value,
            "refresh": parameter.refresh_schedule, "source": parameter.source, **effective,
            "imported": len(fresh), "staleImported": len(imported) - len(fresh),
            "importedSample": fresh[:2],
        })
    return {"market": market, "parameters": rows, "localFeedConfigured": bool(path), "localFeedError": error}
