"""Content-addressed storage and replay of point-in-time monthly research bundles."""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory

import pandas as pd

from .monthly_backtester import month_end_signal
from .monthly_inputs import FACTORS, INPUTS, SOURCES, VETOES, fingerprint, load_frozen_inputs, load_inputs


def bundle_id(hashes):
    canonical = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def archived_folder(store, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{64}", identifier):
        raise ValueError("Enter a 64-character archived bundle fingerprint.")
    folder = Path(store) / identifier
    if not folder.is_dir():
        raise ValueError("That bundle is not in the configured research store.")
    if bundle_id(fingerprint(folder)) != identifier:
        raise ValueError("The archived bundle failed fingerprint verification.")
    return folder


def archive_bundle(source, store):
    source, store = Path(source), Path(store)
    hashes = fingerprint(source)
    identifier = bundle_id(hashes)
    if (store / identifier).exists():
        return archived_folder(store, identifier), identifier
    store.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="intake-", dir=store) as staging:
        copied = Path(staging) / "bundle"
        copied.mkdir()
        for name in INPUTS:
            shutil.copyfile(source / name, copied / name)
        checksums = source / "checksums.json"
        if checksums.is_file():
            shutil.copyfile(checksums, copied / checksums.name)
        if fingerprint(copied) != hashes or fingerprint(source) != hashes:
            raise ValueError("The source bundle changed during archiving. Retry with a stable copy.")
        manifest, *_ = load_inputs(copied)
        if manifest["mode"] != "research":
            raise ValueError("Only declared research bundles can enter the point-in-time store.")
        destination = store / identifier
        try:
            copied.rename(destination)
        except OSError:
            if not destination.is_dir():
                raise
        return archived_folder(store, identifier), identifier


def replay_decision(store, identifier, decision_day, isin):
    if not isinstance(decision_day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", decision_day):
        raise ValueError("Choose a decision date in YYYY-MM-DD format.")
    decision = pd.Timestamp(date.fromisoformat(decision_day))
    if not isinstance(isin, str) or not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
        raise ValueError("Enter the stock's 12-character ISIN.")
    folder = archived_folder(store, identifier)
    hashes, (manifest, prices, snapshots, tri) = load_frozen_inputs(folder)
    if bundle_id(hashes) != identifier:
        raise ValueError("The archived bundle failed fingerprint verification.")
    if manifest["mode"] != "research":
        raise ValueError("Replay requires a declared research bundle.")
    session = tri.index[tri.index.to_period("M") == decision.to_period("M")]
    if not len(session) or session[-1] != decision or not (tri.index > decision).any():
        raise ValueError("Choose a recorded month-end decision with a subsequent market session.")
    scores, snapshot, exposure, scoreable = month_end_signal(prices, snapshots, tri, decision)
    if isin not in snapshot.index:
        raise ValueError("The ISIN was not a member in the archived snapshot on that date.")
    observed = snapshot.loc[isin]
    rank = int(scores.index.get_loc(isin)) + 1 if isin in scores.index else None
    failures = [key for key in VETOES if bool(observed[key])]
    if observed["turnover_crore"] < 25:
        failures.append("liquidity_floor")
    market_inputs = prices.loc[decision].reindex([isin]).iloc[0]
    factors = {key: float(observed[key]) for key in FACTORS}
    for key in ("momentum", "volatility"):
        value = market_inputs[key]
        factors[key] = float(value) if pd.notna(value) else None
    return {
        "bundleId": identifier, "decisionDate": decision_day,
        "knownOn": observed["known_on"].date().isoformat(), "isin": isin, "symbol": str(observed["symbol"]),
        "sector": str(observed["sector"]), "close": float(market_inputs["close"]) if pd.notna(market_inputs["close"]) else None,
        "turnoverCrore": float(observed["turnover_crore"]), "rank": rank, "eligible": len(scores),
        "scoreable": scoreable, "score": float(scores.at[isin, "score"]) if rank else None,
        "targetExposurePct": exposure * 100, "failedChecks": failures,
        "factors": factors,
        "vetoes": {key: bool(observed[key]) for key in VETOES},
        "declaredSources": {key: manifest["sources"][key] for key in SOURCES},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    archive = commands.add_parser("archive")
    archive.add_argument("--data", required=True, type=Path)
    replay = commands.add_parser("replay")
    replay.add_argument("--bundle-id", required=True)
    replay.add_argument("--decision", required=True)
    replay.add_argument("--isin", required=True)
    for command in (archive, replay):
        command.add_argument("--store", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "archive":
            _, identifier = archive_bundle(args.data, args.store)
            result = {"bundleId": identifier}
        else:
            result = replay_decision(args.store, args.bundle_id, args.decision, args.isin)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Research store: {error}\n")


if __name__ == "__main__":
    main()
