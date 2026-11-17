"""Retrieve normalized evidence from operator-configured sources."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .catalogue_evidence import parse_evidence

MAX_FEED_BYTES = 2_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Provider redirected. Configure its final HTTPS endpoint.")


def load_sources(path, members, day, cutoff, market_keys):
    with Path(path).open("rb") as stream:
        raw = stream.read(32_769)
    if len(raw) > 32_768:
        raise ValueError("Source manifest is larger than 32 KB.")
    sources = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(sources, dict) or not 1 <= len(sources) <= 8:
        raise ValueError("Configure one to eight named source endpoints.")
    for name, entry in sources.items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}", name) or not isinstance(entry, dict):
            raise ValueError("Each source needs a short name and an endpoint configuration.")
        url = entry.get("url")
        uri = urlsplit(url) if isinstance(url, str) else None
        if not uri or uri.scheme != "https" or not uri.hostname or uri.username or uri.password or uri.fragment:
            raise ValueError(f"{name}: use an HTTPS endpoint without embedded credentials or a fragment.")
        token = entry.get("bearerEnv")
        if token is not None and (not isinstance(token, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", token)):
            raise ValueError(f"{name}: bearerEnv must name a server environment variable.")

    def fetch(item):
        name, entry = item
        status = {"name": name, "observations": 0, "status": "Unavailable"}
        headers = {"Accept": "application/json"}
        if entry.get("bearerEnv"):
            token = os.environ.get(entry["bearerEnv"])
            if not token:
                return {}, {**status, "status": "Credential missing"}
            headers["Authorization"] = "Bearer " + token
        try:
            request = Request(entry["url"], headers=headers)
            with build_opener(NoRedirect()).open(request, timeout=8) as response:
                raw = response.read(MAX_FEED_BYTES + 1)
            if len(raw) > MAX_FEED_BYTES:
                raise ValueError("Provider payload is larger than 2 MB.")
            parsed = parse_evidence(members, day, cutoff, raw, market_keys, require_isin=True)
            return {key: [{**row, "provider": name} for row in rows] for key, rows in parsed.items()}, {
                **status, "status": "Retrieved", "observations": sum(map(len, parsed.values())),
            }
        except (OSError, ValueError, TypeError, HTTPException):
            return {}, {**status, "status": "Fetch or validation failed"}

    combined = defaultdict(list)
    statuses = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        for bundle, status in executor.map(fetch, sources.items()):
            for key, rows in bundle.items():
                combined[key].extend(rows)
            statuses.append(status)
    return combined, statuses


def consolidate(candidates, risk=False):
    ordered = sorted(candidates, key=lambda row: datetime.fromisoformat(row["asOf"]), reverse=True)
    newest = datetime.fromisoformat(ordered[0]["asOf"])
    competing = ordered if risk else [row for row in ordered if datetime.fromisoformat(row["asOf"]) == newest]
    if any(row["value"] != ordered[0]["value"] for row in competing):
        return None
    return {**ordered[0], "evidence": [
        {"source": row["source"], "asOf": row["asOf"], "provider": row.get("provider", "Local file")}
        for row in ordered
    ]}
