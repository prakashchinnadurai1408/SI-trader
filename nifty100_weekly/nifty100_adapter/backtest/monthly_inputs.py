"""Point-in-time input loader for the monthly Nifty 100 research backtest."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FACTORS = ("quality", "value", "ownership", "earnings_revisions", "news_sentiment")
VETOES = ("asm_gsm", "pledging_veto", "legal_veto", "regulatory_veto", "auditor_veto")
TURNOVER = "traded_value_inr"
PRICE_FIELDS = ("open", "high", "low", "close", "signal_close", "split_ratio", "dividend")
SOURCES = ("prices", "snapshots", "tri")
INPUTS = ("prices.csv", "snapshots.csv", "tri.csv", "manifest.json")


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(folder):
    return {name: file_hash(Path(folder) / name) for name in INPUTS}


def load_frozen_inputs(folder):
    before = fingerprint(folder)
    inputs = load_inputs(folder)
    if fingerprint(folder) != before:
        raise ValueError("The research bundle changed while loading. Retry with a stable copy.")
    return before, inputs


def read_csv(path, required, dates):
    frame = pd.read_csv(path, dtype={"isin": "string", "symbol": "string", "sector": "string"})
    missing = sorted(set(required).difference(frame.columns))
    if missing or frame.empty:
        raise ValueError(f"{path.name}: missing columns {missing} or no data.")
    for column in dates:
        frame[column] = pd.to_datetime(frame[column], format="%Y-%m-%d", errors="raise")
        if frame[column].isna().any():
            raise ValueError(f"{path.name}: blank {column}.")
    return frame


def numeric(frame, columns):
    for column in columns:
        values = pd.to_numeric(frame[column], errors="raise").astype(float)
        if not np.isfinite(values).all():
            raise ValueError(f"{column} must contain finite numbers.")
        frame[column] = values


def load_inputs(folder):
    folder = Path(folder)
    checksum_path = folder / "checksums.json"
    if checksum_path.exists():
        expected = json.loads(checksum_path.read_text(encoding="utf-8"))
        if expected != {name: file_hash(folder / name) for name in INPUTS}:
            raise ValueError("Bundle files differ from the intake checksums.")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict) or manifest.get("mode") not in ("synthetic", "research"):
        raise ValueError("Declare synthetic or research mode in manifest.json.")
    if manifest["mode"] == "research":
        sources = manifest.get("sources", {})
        if not isinstance(sources, dict) or any(not isinstance(sources.get(key), str) or not sources[key].strip() for key in SOURCES):
            raise ValueError("Document the lineage of prices, point-in-time snapshots and TRI in the manifest.")
        if manifest.get("rules_frozen_before_test") is not True:
            raise ValueError("Research mode requires a declared pre-test rules freeze.")
    numeric_costs = ("short_term_tax", "long_term_tax", "dividend_tax")
    for key in numeric_costs:
        value = manifest.get(key)
        if type(value) not in (int, float) or not 0 <= value <= 1:
            raise ValueError(f"Declare {key} as a fraction between 0 and 1 in the manifest.")

    prices = read_csv(folder / "prices.csv", ("date", "isin", *PRICE_FIELDS), ("date",))
    snapshots = read_csv(
        folder / "snapshots.csv", ("date", "known_on", "isin", "symbol", "sector", "turnover_crore", *FACTORS, *VETOES),
        ("date", "known_on"),
    )
    tri = read_csv(folder / "tri.csv", ("date", "tri"), ("date",))
    numeric(prices, PRICE_FIELDS)
    if TURNOVER in prices:
        prices[TURNOVER] = pd.to_numeric(prices[TURNOVER], errors="raise").astype(float)
        observed = prices[TURNOVER].dropna()
        if not np.isfinite(observed).all() or observed.lt(0).any():
            raise ValueError("Daily traded value must be finite and nonnegative when supplied.")
    numeric(snapshots, ("turnover_crore", *FACTORS))
    numeric(tri, ("tri",))
    for frame, key in ((prices, ("date", "isin")), (snapshots, ("date", "isin")), (tri, ("date",))):
        if frame[list(key)].isna().any().any() or frame.duplicated(list(key)).any():
            raise ValueError(f"Missing or duplicate keys: {key}.")
    if any(snapshots[key].fillna("").str.strip().eq("").any() for key in ("isin", "symbol", "sector")):
        raise ValueError("Snapshots require nonblank ISIN, symbol and sector.")
    if prices["isin"].str.strip().eq("").any() or prices["isin"].isna().any():
        raise ValueError("Prices require a nonblank ISIN.")
    if (
        not prices[["open", "high", "low", "close", "signal_close", "split_ratio"]].gt(0).all().all()
        or prices["dividend"].lt(0).any() or tri["tri"].le(0).any()
        or prices["high"].lt(prices[["open", "low", "close"]].max(axis=1)).any()
        or prices["low"].gt(prices[["open", "close"]].min(axis=1)).any()
    ):
        raise ValueError("Invalid OHLC, corporate-action inputs or benchmark.")
    if snapshots["known_on"].gt(snapshots["date"]).any():
        raise ValueError("A snapshot uses data that became known after its decision date.")
    if snapshots["turnover_crore"].lt(0).any():
        raise ValueError("Invalid snapshot turnover.")
    if snapshots.duplicated(["date", "symbol"]).any():
        raise ValueError("Duplicate symbol in a monthly snapshot.")
    for column in VETOES:
        flags = snapshots[column].astype("string").str.lower().str.strip()
        if not flags.isin(("true", "false")).all():
            raise ValueError(f"{column} requires known true/false values.")
        snapshots[column] = flags.eq("true").astype(bool)

    if not prices["date"].isin(tri["date"]).all():
        raise ValueError("TRI does not cover all supplied NSE price dates.")
    prices = prices.sort_values(["isin", "date"])
    session_number = {date: index for index, date in enumerate(tri["date"].sort_values())}
    prices["session_number"] = prices["date"].map(session_number)
    grouped = prices.groupby("isin", sort=False)
    previous_month = grouped["signal_close"].shift(21)
    prices["momentum"] = ((previous_month / grouped["signal_close"].shift(126) - 1)
                          + (previous_month / grouped["signal_close"].shift(252) - 1)) / 2
    complete_history = prices["session_number"].sub(grouped["session_number"].shift(252)).eq(252)
    prices["momentum"] = prices["momentum"].where(complete_history)
    changes = grouped["signal_close"].pct_change(fill_method=None)
    prices["volatility"] = changes.groupby(prices["isin"]).transform(lambda values: values.rolling(63).std())
    return manifest, prices.set_index(["date", "isin"]).sort_index(), snapshots.set_index(["date", "isin"]).sort_index(), tri.set_index("date")["tri"].sort_index()
