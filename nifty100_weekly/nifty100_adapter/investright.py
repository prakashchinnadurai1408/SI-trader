"""Run the weekly strategy and optionally verify the InvestRight API session."""

import argparse
import http.client
import json
import os
from pathlib import Path
from urllib.parse import urlencode


def broker_get(path):
    api_key = os.environ.get("INVESTRIGHT_API_KEY", "").strip()
    token = os.environ.get("INVESTRIGHT_ACCESS_TOKEN", "").strip()
    if not api_key or not token:
        raise ValueError("Set INVESTRIGHT_API_KEY and INVESTRIGHT_ACCESS_TOKEN in PowerShell.")

    query = urlencode({"api_key": api_key})
    connection = http.client.HTTPSConnection("developer.hdfcsec.com", timeout=15)
    try:
        connection.request(
            "GET",
            path + "?" + query,
            headers={"Authorization": token, "User-Agent": "SI-Trader/1.0"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"InvestRight returned HTTP {response.status}.")
        try:
            payload = json.load(response)
        except (ValueError, UnicodeError):
            raise ValueError("InvestRight returned an invalid response.") from None
    except (OSError, http.client.HTTPException):
        raise ValueError("Could not reach the InvestRight holdings API.") from None
    finally:
        connection.close()

    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise ValueError("InvestRight did not confirm a successful API request.")
    return payload.get("data")


def holdings_count():
    holdings = broker_get("/oapi/v1/portfolio/holdings")
    if not isinstance(holdings, list):
        raise ValueError("InvestRight returned an unexpected holdings format.")
    return len(holdings)


def run_strategy(path, top_n):
    import numpy as np
    import pandas as pd

    from .backtest.weekly_backtester import WeeklyBacktester
    from .data.nifty100_universe import get_symbols

    numeric_columns = (
        "close", "daily_turnover_crore", "price_momentum_weekly", "promoter_pledging_pct",
    )
    flag_columns = ("has_pending_legal", "legal_cases_directors", "regulatory_actions")
    required = {"symbol", "asm_status", *numeric_columns, *flag_columns}
    frame = pd.read_csv(path, dtype={"symbol": "string", "asm_status": "string"})
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError("Missing CSV columns: " + ", ".join(missing))
    if frame.empty:
        raise ValueError("The strategy CSV must contain at least one row.")

    frame["symbol"] = frame["symbol"].str.strip().str.upper()
    if frame["symbol"].duplicated().any() or not frame["symbol"].isin(get_symbols()).all():
        raise ValueError("Use one row per symbol from SI-Trader's Nifty 100 universe.")
    frame["asm_status"] = frame["asm_status"].str.strip()
    if frame["asm_status"].fillna("").eq("").any():
        raise ValueError("Provide the surveillance status for every symbol, e.g. NONE.")
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if not np.isfinite(frame[column].to_numpy(dtype=float, na_value=np.nan)).all():
            raise ValueError(f"{column} must contain finite numbers.")
    if not (
        frame["close"].gt(0)
        & frame["daily_turnover_crore"].ge(0)
        & frame["price_momentum_weekly"].gt(-100)
        & frame["promoter_pledging_pct"].between(0, 100)
    ).all():
        raise ValueError("Check the price, turnover, weekly momentum and pledging ranges.")

    for column in flag_columns:
        values = frame[column].astype("string").str.strip().str.lower()
        if not values.isin(("true", "false")).all():
            raise ValueError(f"{column} must contain true or false for each symbol.")
        frame[column] = values.eq("true").astype(bool)

    strategy = WeeklyBacktester(frame, top_n=top_n)
    for parameter in strategy.score_calc.score_params:
        column = parameter.parameter_key
        if column in frame.columns and column not in required:
            strategy.universe[column] = pd.to_numeric(frame[column], errors="raise")
    result = strategy.run_weekly_pipeline()
    if result.get("message"):
        print(result["message"])
    print("Strategy preview complete. Review the basket above.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy-csv", type=Path, help="Point-in-time Nifty 100 strategy inputs")
    parser.add_argument("--check-holdings", action="store_true", help="Verify the InvestRight API login")
    parser.add_argument("--top-n", type=int, default=10, help="Maximum number of candidates")
    args = parser.parse_args()
    if args.top_n < 1 or not (args.strategy_csv or args.check_holdings):
        parser.error("Supply --strategy-csv and/or --check-holdings and a positive --top-n.")

    try:
        if args.check_holdings:
            print(f"InvestRight API access confirmed ({holdings_count()} holdings).")
        if args.strategy_csv:
            run_strategy(args.strategy_csv, args.top_n)
    except (OSError, ValueError) as error:
        parser.exit(1, f"SI-Trader: {error}\n")


if __name__ == "__main__":
    main()
