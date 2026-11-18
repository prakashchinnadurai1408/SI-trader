"""Build and validate the historical input bundle for Gate G1."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

import pandas as pd

from ..data.nse_market import download
from .monthly_backtester import build_signals, research_window
from .monthly_inputs import INPUTS, file_hash, load_inputs, numeric, read_csv

CUTOVER = date(2024, 7, 8)
ARCHIVE_LIMIT = 8_000_000
ACTIONS = ("signal_close", "split_ratio", "dividend")
OHLC = ("open", "high", "low", "close")
EQUITY_SERIES = {"EQ": 0, "BE": 1, "BZ": 2}


def read_tri(path):
    result = pd.read_csv(path, encoding="utf-8-sig")
    result.columns = result.columns.str.strip().str.casefold().str.replace(r"\s+", " ", regex=True)
    for index_col in ("index name", "indexname"):
        if index_col in result:
            result = result.loc[result[index_col].astype("string").str.strip().str.upper() == "NIFTY 100"]
            break
    if "tri" not in result and "total returns index" in result:
        result = result.rename(columns={"total returns index": "tri"})
    if not {"date", "tri"}.issubset(result.columns) or result.empty:
        raise ValueError("Supply the Nifty 100 total-return export with Date and Total Returns Index columns.")
    result = result[["date", "tri"]].copy()
    formats = ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d-%m-%Y", "%d/%m/%Y")
    raw_dates = result["date"].astype("string").str.strip()
    parsed = pd.to_datetime(raw_dates, format=formats[0], errors="coerce")
    for formatting in formats[1:]:
        parsed = parsed.fillna(pd.to_datetime(raw_dates, format=formatting, errors="coerce"))
    result["date"] = parsed
    result["tri"] = result["tri"].astype("string").str.replace(",", "", regex=False)
    numeric(result, ("tri",))
    if result["date"].isna().any() or result["date"].duplicated().any() or result["tri"].le(0).any():
        raise ValueError("TRI requires unique dated positive observations.")
    return result.sort_values("date")


def archive_location(day):
    if day >= CUTOVER:
        name = f"BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
        return name, f"https://nsearchives.nseindia.com/content/cm/{name}"
    month = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")[day.month - 1]
    name = f"cm{day.day:02d}{month}{day.year}bhav.csv.zip"
    return name, f"https://archives.nseindia.com/content/historical/EQUITIES/{day.year}/{month}/{name}"


def archive_rows(path, allowed_isins, expected_day=None):
    try:
        with ZipFile(path) as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
            if len(entries) != 1 or not entries[0].filename.lower().endswith(".csv") or entries[0].file_size > ARCHIVE_LIMIT:
                raise ValueError(f"{path.name}: expected one bounded CSV file.")
            with archive.open(entries[0]) as stream:
                rows = pd.read_csv(stream, dtype="string", encoding="utf-8-sig", index_col=False)
    except (BadZipFile, UnicodeError) as error:
        raise ValueError(f"{path.name}: invalid NSE archive.") from error

    rows.columns = rows.columns.str.strip()
    modern = "TradDt" in rows
    fields = ("TradDt", "ISIN", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric") if modern else (
        "TIMESTAMP", "ISIN", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE",
    )
    if not set(fields).issubset(rows.columns) or rows.empty:
        raise ValueError(f"{path.name}: unrecognized NSE bhavcopy schema.")
    rows = rows[list(fields)].copy()
    rows.columns = ["date", "isin", "series", *OHLC]
    rows["date"] = pd.to_datetime(rows["date"].str.strip(), format="%Y-%m-%d" if modern else "%d-%b-%Y", errors="raise")
    if rows["date"].isna().any() or rows["date"].nunique() != 1:
        raise ValueError(f"{path.name}: expected exactly one dated exchange session.")
    if expected_day is not None and rows["date"].iloc[0].date() != expected_day:
        raise ValueError(f"{path.name}: session date does not match the benchmark calendar.")
    rows["isin"] = rows["isin"].str.strip().str.upper()
    rows["series"] = rows["series"].str.strip().map(EQUITY_SERIES)
    rows = rows.loc[rows["isin"].isin(allowed_isins) & rows["series"].notna()].copy()
    if rows.duplicated(["isin", "series"]).any():
        raise ValueError(f"{path.name}: duplicate security and series.")
    rows = rows.sort_values("series").drop_duplicates("isin")
    numeric(rows, OHLC)
    return rows.drop(columns="series")


def fetch_archives(tri_export, destination, start, end):
    tri = read_tri(tri_export)
    before, after = pd.Timestamp(start), pd.Timestamp(end)
    sessions = list(tri.loc[tri["date"].between(before, after), "date"].dt.date)
    if not sessions:
        raise ValueError("No Nifty 100 TRI sessions in the requested download range.")
    destination.mkdir(parents=True, exist_ok=True)

    def fetch(day):
        name, url = archive_location(day)
        path = destination / name
        if not path.exists():
            content = download(url, ARCHIVE_LIMIT)
            with TemporaryDirectory(dir=destination) as scratch:
                staged = Path(scratch) / name
                staged.write_bytes(content)
                archive_rows(staged, set(), day)
                staged.rename(path)
        else:
            archive_rows(path, set(), day)
        return name

    with ThreadPoolExecutor(max_workers=3) as executor:
        return list(executor.map(fetch, sessions))


def prepare(archives, tri_export, adjustments, snapshots, manifest_path, destination):
    if destination.exists():
        raise ValueError("Use a new output directory.")
    tri = read_tri(tri_export)
    members = read_csv(snapshots, ("date", "isin"), ("date",))
    isins = set(members["isin"].dropna().str.strip().str.upper())
    if not isins:
        raise ValueError("Point-in-time snapshots contain no usable ISINs.")
    actions = read_csv(adjustments, ("date", "isin", *ACTIONS), ("date",))
    actions["isin"] = actions["isin"].str.strip().str.upper()
    actions = actions[["date", "isin", *ACTIONS]]
    if actions[["date", "isin"]].isna().any().any() or actions.duplicated(["date", "isin"]).any():
        raise ValueError("Corporate-action adjustment rows need unique date/ISIN keys.")
    if not archives.is_dir():
        raise ValueError("Supply a folder of legacy and/or UDiFF NSE bhavcopy ZIPs.")
    sessions = []
    for day in tri["date"].dt.date:
        name, _ = archive_location(day)
        file = archives / name
        if file.is_file():
            sessions.append(archive_rows(file, isins, day))
    if not sessions:
        raise ValueError("No NSE archives matched the benchmark dates.")
    prices = pd.concat(sessions, ignore_index=True)
    if prices.empty:
        raise ValueError("No archive prices matched the historical universe.")
    prices = prices.merge(actions, how="left", on=["date", "isin"], validate="one_to_one")
    missing = prices[list(ACTIONS)].isna().any(axis=1)
    if missing.any():
        first = prices.loc[missing, ["date", "isin"]].iloc[0]
        raise ValueError(f"Missing verified adjustment inputs for {missing.sum()} session/security rows; first: {first['date'].date()} {first['isin']}.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as scratch:
        staged = Path(scratch) / "bundle"
        staged.mkdir()
        prices.sort_values(["date", "isin"]).to_csv(staged / "prices.csv", index=False)
        tri.to_csv(staged / "tri.csv", index=False)
        members["isin"] = members["isin"].str.strip().str.upper()
        members.to_csv(staged / "snapshots.csv", index=False)
        shutil.copyfile(manifest_path, staged / "manifest.json")
        load_inputs(staged)
        (staged / "checksums.json").write_text(
            json.dumps({file: file_hash(staged / file) for file in INPUTS}, indent=2), encoding="utf-8",
        )
        staged.rename(destination)
    return len(prices)


def check(folder, start, end, inputs=None):
    result = {"ready": False, "issues": [], "start": start, "end": end}
    if inputs is None:
        result["issues"] = [f"Missing {name}." for name in INPUTS if not (folder / name).is_file()]
    if result["issues"]:
        return result
    try:
        manifest, prices, snapshots, tri = load_inputs(folder) if inputs is None else inputs
        months, dates = research_window(tri, start, end)
        result.update({"sessions": len(dates), "complete_months": len(months), "mode": manifest["mode"]})
        if manifest["mode"] != "research":
            result["issues"].append("A synthetic bundle cannot qualify for Gate G1.")
        if len(months) < 60:
            result["issues"].append("Gate G1 requires at least 60 complete out-of-sample months.")
        session_counts = pd.Series(dates.to_period("M")).value_counts().reindex(months, fill_value=0)
        short = session_counts[session_counts.lt(10)]
        if not short.empty:
            result["issues"].append(f"{len(short)} holdout months have fewer than 10 benchmark sessions; first: {short.index[0]}.")
        missing = dates.difference(prices.index.get_level_values("date").unique())
        if len(missing):
            result["issues"].append(f"Missing NSE prices for {len(missing)} benchmark sessions; first: {missing[0].date()}.")
        marks = tri.groupby(tri.index.to_period("M")).tail(1)
        decisions = marks.index[marks.index.to_period("M").isin(months - 1)]
        sizes = snapshots.groupby(level="date").size().reindex(decisions, fill_value=0)
        unmatched = sizes[sizes.ne(100)]
        if not unmatched.empty:
            result["issues"].append(f"{len(unmatched)} month-ends lack exactly 100 point-in-time members; first: {unmatched.index[0].date()} ({unmatched.iloc[0]}/100).")
        if not len(missing) and unmatched.empty:
            _, result["coverage"] = build_signals(prices, snapshots, tri, dates, months)
    except (KeyError, ValueError, OSError) as error:
        result["issues"].append(str(error))
    result["ready"] = not result["issues"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="Download NSE archives for sessions in a TRI export")
    fetch.add_argument("--tri", required=True, type=Path)
    fetch.add_argument("--out", required=True, type=Path)
    preparation = commands.add_parser("prepare", help="Normalize sources into a Gate G1 bundle")
    for argument in ("archives", "tri", "adjustments", "snapshots", "manifest", "out"):
        preparation.add_argument(f"--{argument}", required=True, type=Path)
    readiness = commands.add_parser("check", help="Validate data readiness without measuring returns")
    readiness.add_argument("--data", required=True, type=Path)
    for command in (fetch, readiness):
        command.add_argument("--start", required=True)
        command.add_argument("--end", required=True)
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            result = {"archive_sessions": len(fetch_archives(args.tri, args.out, args.start, args.end))}
        elif args.command == "prepare":
            result = {"price_records": prepare(args.archives, args.tri, args.adjustments, args.snapshots, args.manifest, args.out)}
        else:
            result = check(args.data, args.start, args.end)
        print(json.dumps(result, indent=2))
        if args.command == "check" and not result["ready"]:
            raise SystemExit(2)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Historical intake: {error}\n")


if __name__ == "__main__":
    main()
