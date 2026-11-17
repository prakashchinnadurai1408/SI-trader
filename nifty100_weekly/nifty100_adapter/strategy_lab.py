"""AlphaDesk-inspired quantitative diagnostics on SI-Trader research data."""

from datetime import datetime
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest.monthly_inputs import load_inputs
from .backtest.compare_strategies import compare_results
from .backtest.historical_intake import check
from .backtest.monthly_backtester import run
from .strategy_builder import challenger_weights
from .data.nse_market import MARKET_TIME, load_nifty100

PRESETS = [
    {"name": "Monthly multifactor", "description": "Frozen Gate G1 baseline using quality, momentum and low volatility."},
    {"name": "Defensive trend", "description": "Research alternative targeting 25% equity below the 10-month Nifty 100 TRI average, and 95% otherwise."},
    {"name": "AI factor challenger", "description": "Export a two-agent weighting proposal and test it on the same holdout."},
]


def pulse():
    frame, market = load_nifty100()
    daily = frame["price_momentum_daily"].dropna()
    five = frame["price_momentum_weekly"].dropna()
    industries = [{
        "name": name, "covered": len(group), "median_five_pct": round(float(group["price_momentum_weekly"].median()), 2),
    } for name, group in frame.dropna(subset=["price_momentum_weekly"]).groupby("industry") if len(group) >= 3]
    industries.sort(key=lambda row: (-row["median_five_pct"], row["name"]))
    return {
        "market": market, "presets": PRESETS, "historyConfigured": bool(os.environ.get("SI_TRADER_STRATEGY_BUNDLE")),
        "breadth": {
            "up": int(daily.gt(0).sum()), "down": int(daily.lt(0).sum()), "flat": int(daily.eq(0).sum()),
            "dailyCovered": len(daily), "medianFivePct": round(float(five.median()), 2),
        },
        "industries": industries,
        "symbols": sorted(frame["symbol"].tolist()),
    }


def diagnostics(prices, tri, horizon, as_of):
    """Use aligned, uninterrupted total-return prices plus raw OHLC for ATR."""
    observed = prices.loc[:as_of].join(tri.loc[:as_of].rename("benchmark"), how="inner")
    dates = tri.loc[:as_of].tail(127).index
    if len(dates) != 127 or not dates.equals(observed.index[-127:]):
        raise ValueError("Diagnostics need 127 consecutive aligned NSE sessions through the analysis date.")
    bars = observed.loc[dates]
    stock = bars["signal_close"]
    returns = np.diff(np.log(stock.to_numpy()))
    market = np.diff(np.log(bars["benchmark"].to_numpy()))
    market_var = float(np.var(market, ddof=1))
    if market_var < 1e-12:
        raise ValueError("The benchmark history has insufficient return variation.")
    beta = float(np.cov(returns, market)[0, 1] / market_var)
    intercept = float((returns.mean() - beta * market.mean()) * 252)
    ewma = float(pd.Series(returns ** 2).ewm(alpha=0.06, adjust=False).mean().iloc[-1])
    if ewma <= 0:
        raise ValueError("The stock history has insufficient return variation.")
    adjusted_change = stock.diff().tail(14)
    up = float(adjusted_change.clip(lower=0).mean())
    down = float(-adjusted_change.clip(upper=0).mean())
    rsi = 50 if up == 0 and down == 0 else 100 if down == 0 else 100 - 100 / (1 + up / down)
    previous = bars["close"].shift(1).div(bars["split_ratio"])
    atr = float(pd.concat([bars["high"] - bars["low"], (bars["high"] - previous).abs(),
                            (bars["low"] - previous).abs()], axis=1).max(axis=1).tail(14).mean())
    # Zero log drift isolates variability. Percentiles are simulated scenarios and are not calibrated odds.
    shocks = np.random.default_rng(42).standard_t(5, (3000, horizon)) / np.sqrt(5 / 3)
    paths = np.expm1(np.cumsum(np.sqrt(ewma) * shocks, axis=1)) * 100
    if not np.isfinite(paths).all():
        raise ValueError("The history contains extreme values incompatible with the stress model.")
    fan = np.percentile(paths, (5, 25, 50, 75, 95), axis=0).T
    return {
        "asOf": as_of.date().isoformat(), "sessions": len(bars), "close": float(bars["close"].iloc[-1]),
        "metrics": {
            "beta": round(beta, 3), "annualizedInterceptPct": round(intercept * 100, 2),
            "ewmaVolPct": round(np.sqrt(ewma * 252) * 100, 2),
            "momentum21Pct": round(float(stock.iloc[-1] / stock.iloc[-22] - 1) * 100, 2),
            "momentum63Pct": round(float(stock.iloc[-1] / stock.iloc[-64] - 1) * 100, 2),
            "rsi14": round(rsi, 1), "atr14": round(atr, 2),
        },
        "stress": {"assumption": "Zero log drift, fat-tailed shocks, 3,000 paths", "percentiles": [5, 25, 50, 75, 95],
                   "days": list(range(horizon + 1)), "returnsPct": [[0.0] * 5, *fan.round(2).tolist()]},
    }


def run_comparison(payload):
    start, end = payload.get("start"), payload.get("end")
    capital = payload.get("capital")
    if any(not isinstance(month, str) or not re.fullmatch(r"[1-9][0-9]{3}-(0[1-9]|1[0-2])", month)
           for month in (start, end)):
        raise ValueError("Choose a first and last holdout month.")
    if start > end or end >= datetime.now(MARKET_TIME).strftime("%Y-%m"):
        raise ValueError("Choose an ordered holdout ending in a completed month.")
    if type(capital) not in (int, float) or not 1 <= capital <= 1_000_000_000:
        raise ValueError("Enter starting capital between INR 1 and INR 1 billion.")
    run_test = payload.get("run")
    if type(run_test) is not bool:
        raise ValueError("Choose a readiness check or strategy comparison.")
    proposal = payload.get("challenger")
    weights = challenger_weights(proposal) if proposal is not None else None
    configured = os.environ.get("SI_TRADER_STRATEGY_BUNDLE")
    if not configured:
        return {"readiness": {"ready": False, "issues": [
            "Set SI_TRADER_STRATEGY_BUNDLE to a prepared research bundle in the server environment."
        ]}}
    folder = Path(configured)
    readiness = check(folder, start, end)
    result = {"readiness": readiness}
    if not readiness["ready"] or not run_test:
        return result

    equity, baseline = run(folder, start, end, capital)
    defensive_equity, defensive = run(folder, start, end, capital, defensive=True)
    result.update({
        "baselineGate": baseline["gate_g1"],
        "capital": capital,
        "inputSha256": baseline["input_sha256"],
        "comparisons": [compare_results(baseline, equity, defensive, defensive_equity)],
    })
    if weights is not None:
        challenger_equity, challenger = run(folder, start, end, capital, weights=weights)
        result["comparisons"].append(compare_results(baseline, equity, challenger, challenger_equity))
    return result


def run_diagnostics(symbol, horizon, folder=None):
    if type(horizon) is not int or not 5 <= horizon <= 30:
        raise ValueError("Choose a stress horizon of 5 to 30 trading sessions.")
    path = folder or os.environ.get("SI_TRADER_STRATEGY_BUNDLE")
    if not path:
        raise ValueError("Configure SI_TRADER_STRATEGY_BUNDLE with the point-in-time research dataset.")
    manifest, prices, snapshots, tri = load_inputs(Path(path))
    if manifest["mode"] != "research":
        raise ValueError("Strategy Lab diagnostics require a declared research bundle; synthetic mode is ineligible.")
    latest_prices = prices.index.get_level_values("date").max()
    as_of = min(latest_prices, tri.index[-1], pd.Timestamp(datetime.now(MARKET_TIME).date()))
    mapping = snapshots.reset_index()
    latest_date = mapping.loc[mapping["date"].le(as_of), "date"].max()
    candidates = mapping.loc[mapping["date"].eq(latest_date) & mapping["symbol"].eq(symbol), "isin"].unique()
    if len(candidates) != 1:
        raise ValueError("The latest covered membership snapshot must map the selected symbol to one ISIN.")
    if candidates[0] not in prices.index.get_level_values("isin"):
        raise ValueError("The mapped ISIN has no price history in this bundle.")
    # The TRI bundle can intentionally extend one session beyond equity coverage.
    series = prices.xs(candidates[0], level="isin")
    if series.index[-1] < as_of:
        raise ValueError("The selected stock lacks a close on the latest covered market session.")
    return {"symbol": symbol, "source": "Configured research bundle", **diagnostics(series, tri, horizon, as_of)}
