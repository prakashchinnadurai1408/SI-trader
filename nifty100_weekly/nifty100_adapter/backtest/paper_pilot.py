"""Approval-gated, six-rebalance SI-Trader paper pilot. No broker order path."""

import argparse
from contextlib import closing, contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

from .gate_g1 import gate_g1
from .monthly_backtester import (
    DRAWDOWN_ALERT, STOP, TURNOVER_CAP, Holding, Lot, Portfolio, month_end_signal,
)
from .monthly_inputs import VETOES, file_hash, load_inputs

MARKET_TIME = timezone(timedelta(hours=5, minutes=30))
PILOT_LENGTH = 6


def clock():
    return datetime.now(MARKET_TIME)


def verified_gate(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    manifest = report["data_manifest"]
    if (
        report["gate_g1"]["status"] != "pass"
        or manifest.get("mode") != "research"
        or manifest.get("rules_frozen_before_test") is not True
    ):
        raise ValueError("The paper pilot requires a qualifying research-mode Gate G1 pass.")
    equity_path = report_path.with_name("daily_equity.csv")
    equity = pd.read_csv(equity_path, index_col="date", parse_dates=["date"])
    for column in ("equity", "benchmark"):
        equity[column] = pd.to_numeric(equity[column], errors="raise")
    if equity.empty or not equity.index.is_unique or not equity.index.is_monotonic_increasing:
        raise ValueError("Gate G1 equity dates must be unique and chronological.")
    levels = equity[["equity", "benchmark"]]
    if not np.isfinite(levels.to_numpy()).all() or not levels.gt(0).all().all():
        raise ValueError("Gate G1 equity and benchmark values must be finite and positive.")
    months = pd.period_range(report["start_month"], report["end_month"], freq="M")
    if len(months) < 60 or not equity.index.to_period("M").unique().equals(months.insert(0, months[0] - 1)):
        raise ValueError("Gate G1 equity does not cover the declared 60-month minimum holdout.")
    sessions = equity.groupby(equity.index.to_period("M")).size()
    coverage = report["coverage"]
    if (
        sessions.iloc[0] != 1 or sessions.iloc[1:].lt(10).any()
        or len(coverage) != len(months)
        or [item["execution"][:7] for item in coverage] != [str(month) for month in months]
        or any(item["execution"] not in equity.index or item["scoreable"] < 90 for item in coverage)
    ):
        raise ValueError("Gate G1 report lacks daily equity or monthly decision coverage.")
    if gate_g1(equity, months, True)["status"] != "pass":
        raise ValueError("Recalculated Gate G1 metrics did not pass.")
    return {"end": str(months[-1]), "report_sha256": file_hash(report_path),
            "equity_sha256": file_hash(equity_path), "tax": {
                key: _tax_rate(manifest, key) for key in ("short_term_tax", "long_term_tax", "dividend_tax")
            }}


def _tax_rate(manifest, key):
    value = manifest.get(key)
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise ValueError(f"Gate G1 report lacks valid {key}.")
    return value


@contextmanager
def ledger(path, create=False):
    if not create and not path.is_file():
        raise ValueError("Initialize the paper pilot with a qualifying Gate G1 report first.")
    with closing(sqlite3.connect(path, isolation_level="IMMEDIATE")) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if create:
            db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id = 1), value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL)")
        yield db


def load_state(db):
    row = db.execute("SELECT value FROM state WHERE id = 1").fetchone()
    if row is None:
        raise ValueError("Paper pilot ledger is not initialized.")
    return json.loads(row[0])


def save(db, state, kind, detail, now):
    db.execute("INSERT INTO state VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET value = excluded.value",
               (json.dumps(state, allow_nan=False),))
    db.execute("INSERT INTO events(at, kind, detail) VALUES(?, ?, ?)",
               (now.isoformat(), kind, json.dumps(detail, allow_nan=False)))


def initialize(path, report, capital, now):
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("Starting paper capital must be finite and positive.")
    gate = verified_gate(report)
    with ledger(path, create=True) as db:
        if db.execute("SELECT 1 FROM state").fetchone():
            raise ValueError("This paper pilot is already initialized.")
        state = {"gate": gate, "capital": capital, "cash": capital, "peak": capital,
                 "holdings": {}, "plan": None, "marks": [], "completed": [], "skipped": []}
        save(db, state, "initialized", {"capital": capital, "gate": gate}, now)
        return status(state)


def restore(state):
    portfolio = Portfolio(state["cash"], state["gate"]["tax"])
    for isin, item in state["holdings"].items():
        lots = [Lot(pd.Timestamp(lot["bought"]), lot["quantity"], lot["basis"]) for lot in item["lots"]]
        portfolio.holdings[isin] = Holding(item["symbol"], item["sector"], lots, item["peak"], item["stopped"])
    return portfolio


def freeze(state, portfolio):
    state["cash"] = portfolio.cash
    state["holdings"] = {}
    for isin, holding in portfolio.holdings.items():
        item = asdict(holding)
        for lot in item["lots"]:
            lot["bought"] = lot["bought"].date().isoformat()
        state["holdings"][isin] = item


def inputs(folder, state):
    manifest, prices, snapshots, tri = load_inputs(folder)
    if manifest["mode"] != "research" or any(manifest[key] != rate for key, rate in state["gate"]["tax"].items()):
        raise ValueError("Pilot requires a research bundle with the Gate G1 tax assumptions.")
    return prices, snapshots, tri


def mark_day(state, portfolio, quotes, benchmark, day, weekly):
    nav = portfolio.equity(quotes, "close")
    state["peak"] = max(state["peak"], nav)
    state["marks"].append({"date": day.date().isoformat(), "equity": nav, "cash": portfolio.cash,
                           "benchmark": float(benchmark)})
    for isin, holding in portfolio.holdings.items():
        close = portfolio.quote(quotes, isin, "close")
        holding.peak = max(holding.peak, close)
        if weekly and not holding.stopped and close <= holding.peak * (1 - STOP):
            holding.stopped = True
            portfolio.alerts.append({"date": str(day.date()), "type": "weekly_stop", "symbol": holding.symbol})
    if weekly and nav <= state["peak"] * (1 - DRAWDOWN_ALERT):
        portfolio.alerts.append({"date": str(day.date()), "type": "weekly_drawdown", "value": 1 - nav / state["peak"]})


def mark_through(state, portfolio, prices, tri, through, observed_through, initialize_at=None):
    if through not in tri.index:
        raise ValueError(f"No benchmark close for {through.date()}.")
    if not state["marks"]:
        if initialize_at is None:
            raise ValueError("Prepare the first rebalance before marking the portfolio.")
        state["marks"].append({"date": str(initialize_at.date()), "equity": state["capital"],
                               "cash": state["capital"], "benchmark": float(tri.at[initialize_at])})
    last = pd.Timestamp(state["marks"][-1]["date"])
    if through < last:
        raise ValueError("Cannot mark before the last recorded close.")
    calendar = tri.index[tri.index <= through]
    weekly_ends = set(calendar.to_series().groupby(calendar.to_period("W-FRI")).max())
    friday = through.to_period("W-FRI").end_time.date()
    if observed_through < friday:
        weekly_ends.discard(through)
    for day in calendar[(calendar > last)]:
        portfolio.day = day
        quotes = prices.loc[day]
        portfolio.actions(quotes)
        mark_day(state, portfolio, quotes, tri.at[day], day, day in weekly_ends)
    freeze(state, portfolio)


def session_day(value):
    parsed = datetime.strptime(value, "%Y-%m-%d")
    if parsed.date().isoformat() != value:
        raise ValueError("Dates must use YYYY-MM-DD.")
    return pd.Timestamp(parsed)


def close_available(through, now):
    if through.date() > now.date() or (through.date() == now.date() and now.hour < 17):
        raise ValueError("A current-day paper mark or fill requires a published close after 17:00 IST.")


def prepare_plan(path, folder, decision, execution, now):
    if not decision.date() <= now.date() < execution.date():
        raise ValueError("Prepare and approve after the decision close and before the execution date.")
    close_available(decision, now)
    month = execution.to_period("M")
    if decision.to_period("M") + 1 != month or (execution - decision).days > 10:
        raise ValueError("Execution must be in the month immediately after the decision date.")
    with ledger(path) as db:
        state = load_state(db)
        if state["plan"] or len(state["completed"]) >= PILOT_LENGTH:
            raise ValueError("Resolve the current proposal first, or the six-rebalance pilot is complete.")
        processed = state["completed"] + state["skipped"]
        if str(month) <= state["gate"]["end"] or (processed and str(month) != str(max(pd.Period(item["month"], freq="M") for item in processed) + 1)):
            raise ValueError("Use the next consecutive pilot month after the Gate G1 holdout.")
        prices, snapshots, tri = inputs(folder, state)
        observed = tri.index[tri.index <= pd.Timestamp(now.date())]
        if len(observed) == 0 or observed[-1] != decision:
            raise ValueError("Decision must be the latest observed benchmark session before execution.")
        scores, snapshot, exposure, scoreable = month_end_signal(prices, snapshots, tri, decision)
        portfolio = restore(state)
        mark_through(state, portfolio, prices, tri, decision, now.date(), initialize_at=decision)
        weights, exits = portfolio.target_weights(scores, snapshot, exposure, decision)
        changes = []
        for isin in dict.fromkeys([*weights, *portfolio.holdings]):
            holding = portfolio.holdings.get(isin)
            target = weights.get(isin, 0)
            symbol = scores.at[isin, "symbol"] if isin in scores.index else holding.symbol
            change = "Keep" if holding and target else "Add" if target else "Remove"
            changes.append({"isin": isin, "symbol": symbol, "action": change,
                            "held_quantity": holding.quantity if holding else 0, "target_weight": target,
                            "reason": exits.get(isin, "")})
        plan = {
            "month": str(month), "decision": str(decision.date()), "execution": str(execution.date()),
            "status": "pending", "changes": changes, "scoreable": scoreable, "eligible": len(scores),
            "exposure": exposure, "scores": scores[["symbol", "sector", "close"]].reset_index().to_dict("records"),
            "snapshot": snapshot[["sector", *VETOES]].reset_index().to_dict("records"),
        }
        state["plan"] = plan
        save(db, state, "proposal", {**public_plan(plan), "weekly_alerts": portfolio.alerts}, now)
        return public_plan(plan)


def public_plan(plan):
    return {key: value for key, value in plan.items() if key not in ("scores", "snapshot")}


def review(path, approve, reviewer, now):
    if not reviewer.strip():
        raise ValueError("Record a reviewer name.")
    with ledger(path) as db:
        state = load_state(db)
        plan = state["plan"]
        if not plan or (approve and plan["status"] != "pending"):
            raise ValueError("There is no pending paper proposal to review.")
        if approve and now.date() >= session_day(plan["execution"]).date():
            raise ValueError("Approve before the execution date. An expired proposal can only be skipped.")
        plan["status"] = "approved" if approve else "skipped"
        plan["reviewer"] = reviewer.strip()
        plan["reviewed_at"] = now.isoformat()
        detail = public_plan(plan)
        if not approve:
            state["skipped"].append(detail)
            state["plan"] = None
        save(db, state, plan["status"], detail, now)
        return detail


def record_fill(path, folder, now):
    with ledger(path) as db:
        state = load_state(db)
        plan = state["plan"]
        if not plan or plan["status"] != "approved":
            raise ValueError("Paper fills require a recorded approval.")
        day = session_day(plan["execution"])
        decision = session_day(plan["decision"])
        close_available(day, now)
        prices, _, tri = inputs(folder, state)
        following = tri.index[(tri.index > decision) & (tri.index <= day)]
        if len(following) != 1 or following[0] != day:
            raise ValueError("Execution must be the first recorded trading session after the approved decision.")
        portfolio = restore(state)
        portfolio.day = day
        quotes = prices.loc[day]
        portfolio.actions(quotes)
        open_nav = portfolio.equity(quotes, "open")
        scores = pd.DataFrame(plan["scores"], columns=["isin", "symbol", "sector", "close"]).set_index("isin")
        snapshot = pd.DataFrame(plan["snapshot"]).set_index("isin")
        portfolio.rebalance(quotes, scores, snapshot, plan["exposure"], decision)
        mark_day(state, portfolio, quotes, tri.at[day], day, day.weekday() == 4)
        freeze(state, portfolio)
        turnover = sum(trade["open"] * trade["quantity"] for trade in portfolio.trades) / open_nav
        detail = {"month": plan["month"], "execution": plan["execution"], "reviewer": plan["reviewer"],
                  "fills": portfolio.trades, "turnover": turnover, "forced_exit_turnover": turnover > TURNOVER_CAP + 1e-9,
                  "alerts": portfolio.alerts}
        state["completed"].append(detail)
        state["plan"] = None
        save(db, state, "simulation", detail, now)
        return detail


def record_marks(path, folder, day, now):
    close_available(day, now)
    with ledger(path) as db:
        state = load_state(db)
        if state["plan"] and day >= session_day(state["plan"]["execution"]):
            raise ValueError("Record or skip the pending rebalance before advancing past its execution date.")
        prices, _, tri = inputs(folder, state)
        portfolio = restore(state)
        mark_through(state, portfolio, prices, tri, day, now.date())
        detail = {"through": str(day.date()), "alerts": portfolio.alerts}
        save(db, state, "weekly_monitoring", detail, now)
        return detail


def status(state):
    last = state["marks"][-1] if state["marks"] else None
    first = state["marks"][0] if state["marks"] else None
    return {
        "mode": "paper", "rebalance_target": PILOT_LENGTH, "completed_rebalances": len(state["completed"]),
        "skipped_rebalances": len(state["skipped"]), "pilot_review_due": len(state["completed"]) >= PILOT_LENGTH,
        "cash": state["cash"], "last_mark": last,
        "holdings": [{"isin": isin, "symbol": row["symbol"], "quantity": sum(lot["quantity"] for lot in row["lots"])}
                     for isin, row in state["holdings"].items()],
        "paper_return": last["equity"] / first["equity"] - 1 if last else None,
        "benchmark_return": last["benchmark"] / first["benchmark"] - 1 if last else None,
        "plan": public_plan(state["plan"]) if state["plan"] else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--g1-report", required=True, type=Path)
    init.add_argument("--capital", required=True, type=float)
    plan = commands.add_parser("plan")
    plan.add_argument("--decision", required=True, type=session_day)
    plan.add_argument("--execution", required=True, type=session_day)
    fill = commands.add_parser("fill")
    marks = commands.add_parser("mark")
    marks.add_argument("--through", required=True, type=session_day)
    for command in (plan, fill, marks):
        command.add_argument("--data", required=True, type=Path)
    for action in ("approve", "skip"):
        commands.add_parser(action).add_argument("--reviewer", required=True)
    commands.add_parser("status")
    commands.add_parser("audit")
    args = parser.parse_args()
    now = clock()
    try:
        if args.command == "init":
            result = initialize(args.ledger, args.g1_report, args.capital, now)
        elif args.command == "plan":
            result = prepare_plan(args.ledger, args.data, args.decision, args.execution, now)
        elif args.command in ("approve", "skip"):
            result = review(args.ledger, args.command == "approve", args.reviewer, now)
        elif args.command == "fill":
            result = record_fill(args.ledger, args.data, now)
        elif args.command == "mark":
            result = record_marks(args.ledger, args.data, args.through, now)
        else:
            with ledger(args.ledger) as db:
                result = status(load_state(db)) if args.command == "status" else [
                    {"at": at, "kind": kind, "detail": json.loads(detail)}
                    for at, kind, detail in db.execute("SELECT at, kind, detail FROM events ORDER BY id")
                ]
        print(json.dumps(result, indent=2, allow_nan=False))
    except (TypeError, KeyError, ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Paper pilot: {error}\n")


if __name__ == "__main__":
    main()
