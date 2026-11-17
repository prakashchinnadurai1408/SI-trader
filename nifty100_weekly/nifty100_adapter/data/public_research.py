"""Supplement the catalogue with dated exchange and regulator observations."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree

from .catalogue_evidence import actions_data, announcements_data, observation
from .nse_market import MARKET_TIME, download

SEBI_RSS = "https://www.sebi.gov.in/sebirss.xml"


def exchange_disclosures(members, day, cutoff):
    rows = announcements_data(members, day, cutoff)["company_news"]
    return {"company_news": {item["symbol"]: {**item, "value": item["value"]["exchange_category"]} for item in rows}}


def exchange_actions(members, day, cutoff):
    data = actions_data(members, day, cutoff)
    result = {"corporate_actions": {}, "corporate_action_dividends": {}}
    for key, rows in data.items():
        if key not in result:
            continue
        for item in rows:
            newest = item["value"][0]
            value = True if key == "corporate_actions" else newest["subject"]
            result[key][item["symbol"]] = {**item, "asOf": newest["ex_date"], "value": value}
    return result


def regulator_announcements(members, day, cutoff):
    raw = download(SEBI_RSS, 500_000)
    if b"<!doctype" in raw.lower():
        raise ValueError("Unexpected SEBI feed document type.")
    root = ElementTree.fromstring(raw)
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise ValueError("Unexpected SEBI RSS feed format.")
    dated = []
    for item in channel.findall("item"):
        link = item.findtext("link", "").strip()
        title = item.findtext("title", "").strip()
        uri = urlsplit(link)
        try:
            stamp = parsedate_to_datetime(item.findtext("pubDate", ""))
        except (ValueError, TypeError, OverflowError):
            continue
        if (uri.scheme == "https" and uri.netloc == "www.sebi.gov.in" and title
                and stamp.tzinfo and stamp <= cutoff and 0 <= (day - stamp.astimezone(MARKET_TIME).date()).days <= 30):
            dated.append((stamp, link, title[:180]))
    if not dated:
        return {"regulator_announcements": {}}
    dated.sort(reverse=True)
    stamp, source, title = dated[0]
    return {"regulator_announcements": {"*": {
        **observation("*", True, stamp, source), "headline": title,
    }}}


PUBLIC_FEEDS = [
    ("NSE corporate disclosures", exchange_disclosures),
    ("NSE corporate actions", exchange_actions),
    ("SEBI announcements", regulator_announcements),
]


def collect_public_records(members, day, cutoff):
    def fetch(spec):
        name, loader = spec
        try:
            records = loader(members, day, cutoff)
            count = sum(map(len, records.values()))
            return records, {"name": name, "status": "Retrieved" if count else "No dated observations", "observations": count}
        except (ElementTree.ParseError, OSError, ValueError, KeyError, TypeError):
            return {}, {"name": name, "status": "Fetch or validation failed", "observations": 0}

    with ThreadPoolExecutor(max_workers=len(PUBLIC_FEEDS)) as pool:
        results = list(pool.map(fetch, PUBLIC_FEEDS))
    return {key: records for bundle, _ in results for key, records in bundle.items()}, [
        status for _, status in results
    ]
