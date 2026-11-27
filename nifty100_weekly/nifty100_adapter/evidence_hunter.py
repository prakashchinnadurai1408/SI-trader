"""Find source gaps without turning retrieved pages into invented observations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import os
from urllib.parse import urlsplit, quote

from .ai_parameters import PARAMETERS
from .config.parameter_catalogue import RoleType
from .data.data_source_catalogue import PARAMETER_TO_DATA_SOURCE
from .data.nse_market import load_nifty100, download
from .full_catalogue import readiness
from .research_jobs import progress
from .strategy_builder import agent

OFFICIAL = {"www.nseindia.com", "nsearchives.nseindia.com", "www.bseindia.com",
            "api.bseindia.com", "www.sebi.gov.in", "www.rbi.org.in", "pib.gov.in", "www.pib.gov.in"}
FALLBACKS = [
    ("SEBI filings directory", "https://www.sebi.gov.in/curation/corporate_filings.html"),
    ("RBI releases", "https://www.rbi.org.in/pressreleases_rss.xml"),
    ("PIB releases", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1"),
]


def gap_plan(coverage):
    rows = []
    for item in coverage["parameters"]:
        definition = PARAMETERS[item["key"]]
        source = PARAMETER_TO_DATA_SOURCE.get(item["key"])
        critical = definition.role_type in (RoleType.FILTER, RoleType.VETO)
        rows.append({**item, "sourceName": source.source_name if source else definition.source,
            "endpoint": source.api_endpoint if source else "", "refresh": definition.refresh_schedule,
            "priority": 1 if critical else 2 if definition.role_type == RoleType.SCORE else 3,
            "nextAction": "Current evidence validated" if item["ready"] else
                "Resolve conflicting/invalid observations" if item["invalid"] or item["conflicts"] else
                "Retrieve dated issuer/primary-source evidence and normalize to the required value contract",
            "credentialRequired": bool(source and source.requires_auth),
            "credentialConfigured": bool(source and source.api_key_env_var and os.environ.get(source.api_key_env_var)),
        })
    return sorted(rows, key=lambda row: (row["ready"], row["priority"], row["key"]))


def hunt(payload, initial=None):
    progress("Hunter: refreshing primary and configured evidence feeds")
    if initial is None:
        frame, market = load_nifty100()
        coverage, _ = readiness(frame, market)
    else:
        frame, market, coverage = initial
    plan = gap_plan(coverage)
    # Probe one constituent per source, never imply that a probe covers all 100 stocks.
    symbol = sorted(frame.symbol)[0]
    from datetime import date
    day = date.fromisoformat(market["asOf"])
    probes = dict(FALLBACKS)
    blocked = []
    for row in plan:
        if row["ready"]:
            continue
        url = row["endpoint"]
        if row["credentialRequired"]:
            blocked.append({"source": row["sourceName"], "reason": "Use a configured normalized provider connector; credentials alone do not supply a parser."})
            continue
        if urlsplit(url).hostname not in OFFICIAL:
            continue
        for key, value in {"symbol": quote(symbol), "date": str(day), "from_date": str(day-timedelta(days=365)), "to_date": str(day)}.items():
            url = url.replace("{"+key+"}", value)
        if "{" not in url and len(probes) < 12:
            probes.setdefault(row["sourceName"], url)

    def fetch(item):
        name, url = item
        try:
            raw = download(url, 500_000)
            return {"source": name, "url": url, "status": "Retrieved candidate document",
                    "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                    "validation": "Not promoted to a factor value; dated field extraction and validation required"}
        except (OSError, ValueError):
            return {"source": name, "url": url, "status": "Unavailable or rejected", "bytes": 0,
                    "validation": "Retry through an approved connector or obtain the issuer filing"}

    progress("Hunter: checking alternate primary sources in parallel")
    with ThreadPoolExecutor(max_workers=4) as pool:
        attempts = list(pool.map(fetch, probes.items()))
    priority_method, ai_error = "Risk-first rules", ""
    model = payload.get("model")
    if model:
        progress("Hunter agent: prioritizing the missing research inputs")
        keys = [row["key"] for row in plan if not row["ready"]]
        if keys:
            try:
                result = agent(model, "Prioritize up to eight missing parameter keys for evidence acquisition. "
                    "Risk vetoes and filters come first. Never invent facts, claim source coverage or approve investments.",
                    {"gaps": [{k: row[k] for k in ("key", "role", "available", "expected", "priority")} for row in plan if not row["ready"]]},
                    {"type": "object", "required": ["priority"], "additionalProperties": False,
                     "properties": {"priority": {"type": "array", "maxItems": 8, "items": {"type": "string", "enum": keys}}}})
                selected = result.get("priority")
                if not isinstance(selected, list) or len(selected)>8 or any(key not in keys for key in selected):
                    raise ValueError("Invalid prioritization")
                order = {key: i for i, key in enumerate(dict.fromkeys(selected))}
                plan.sort(key=lambda row: (row["ready"], row["priority"], order.get(row["key"], 99)))
                priority_method = "AI-assisted, with mandatory risk-first ordering"
            except ValueError:
                ai_error = "AI prioritization unavailable; source retrieval and the risk-first work queue are retained."
    return {"market": market, "complete": coverage["complete"], "total": len(plan), "parameters": plan,
            "attempts": attempts, "blockers": list({row["source"]: row for row in blocked}.values()),
            "sourceFeeds": coverage["sourceFeeds"], "priorityMethod": priority_method, "aiError": ai_error,
            "probeSymbol": symbol, "tradeEligible": False,
            "note": "A fetched page is a candidate source, not verified coverage. No observations or risk clearances are fabricated."}
