"""Rank weekly paper candidates using the validated catalogue."""

import pandas as pd

from .ai_parameters import PARAMETERS
from .config.parameter_catalogue import RoleType
from .full_catalogue import MARKET_FACTORS, RATES, weekly_risk_screen


def weekly_candidates(frame, coverage, records):
    universe, rejected = weekly_risk_screen(frame, records)
    weights = {
        row["key"]: max(1, PARAMETERS[row["key"]].weight)
        for row in coverage["parameters"]
        if row["ready"] and PARAMETERS[row["key"]].role_type == RoleType.SCORE
    }
    if universe.empty or not weights:
        return [], {}, rejected

    factors = pd.DataFrame({
        key: {symbol: records[key][symbol]["value"] for symbol in universe["symbol"]}
        for key in weights
    })
    ranks = factors.rank(pct=True)
    if "pe_ratio_vs_sector" in weights:
        ranks["pe_ratio_vs_sector"] = factors["pe_ratio_vs_sector"].rank(pct=True, ascending=False)
    total = sum(weights.values())
    weights = {key: weight / total * 100 for key, weight in weights.items()}
    scores = ranks.mul(pd.Series(weights)).sum(axis=1).sort_index().sort_values(ascending=False, kind="stable")
    members = universe.set_index("symbol")

    risk_keys = [key for key in PARAMETERS if key in rejected]
    context_keys = [
        key for key, definition in PARAMETERS.items()
        if definition.role_type in (RoleType.ADVISORY, RoleType.FLAG) and key not in MARKET_FACTORS
    ]
    candidates = []
    for symbol, score in scores.items():
        stock = members.loc[symbol]
        flags = [
            key for key in context_keys if PARAMETERS[key].role_type == RoleType.FLAG
            and records[key].get(symbol, {}).get("value") is True
        ]
        # Limit free text in the planner prompt; the report retains every observed row.
        notes = {
            key: str(records[key][symbol]["value"])[:90]
            for key in context_keys if PARAMETERS[key].role_type == RoleType.ADVISORY and symbol in records[key]
        }
        drivers = ranks.loc[symbol].sub(0.5).mul(pd.Series(weights)).abs().nlargest(3).index
        candidates.append({
            "symbol": symbol, "company_name": stock["company_name"], "price": float(stock["close"]),
            "score": round(float(score), 2),
            "rankDrivers": {key: round(float(factors.at[symbol, key]), 3) for key in drivers},
            "unknownRiskCount": sum(("*" if key in MARKET_FACTORS else symbol) not in records[key] for key in risk_keys),
            **({"flags": flags[:4]} if flags else {}),
            **({"evidenceNotes": dict(list(notes.items())[:2])} if notes else {}),
        })
    return candidates, weights, rejected


def weekly_context(coverage, records):
    market_values = {key: records[key]["*"]["value"] for key in sorted(MARKET_FACTORS - RATES) if "*" in records[key]}
    dials = {
        key: value for key, value in market_values.items()
        if PARAMETERS[key].role_type == RoleType.MARKET_DIAL
    }
    return {
        "asOf": coverage["market"]["asOf"],
        "coverage": {row["key"]: [row["role"], row["available"]] for row in coverage["parameters"]},
        "market": market_values,
    }, dials
