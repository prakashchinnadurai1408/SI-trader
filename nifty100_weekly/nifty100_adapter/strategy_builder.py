"""Create an AI challenger that can be tested against the frozen monthly baseline."""

from datetime import datetime, timezone
import json
from statistics import median

from .ai_strategy import ollama
from .backtest.monthly_backtester import WEIGHTS

OBJECTS = {"type": "object", "additionalProperties": False}
DIMENSIONS = {
    "quality": "Point-in-time company fundamentals",
    "momentum": "6- and 12-month adjusted price momentum excluding the most recent month",
    "volatility": "63-session realized volatility",
    "value": "Point-in-time valuation score",
    "ownership": "Point-in-time ownership score",
    "earnings_revisions": "Point-in-time earnings revisions",
    "news_sentiment": "Point-in-time sentiment score",
}
RISKS = {
    "data_coverage": "Missing or uneven historical factor or risk coverage",
    "point_in_time": "Look-ahead or survivorship bias",
    "turnover": "Trading costs, taxes and turnover",
    "factor_concentration": "Factor concentration and regime dependence",
    "execution": "Simulated fills and implementation shortfall",
    "overfitting": "Overfitting the challenger to selected dates",
}
TILTS = {
    "quality": "Test whether adding weight to quality improves holdout net return.",
    "momentum": "Test whether adding weight to momentum improves holdout net return.",
    "volatility": "Test whether adding weight to low volatility improves holdout net return.",
    "balanced": "Test whether a more balanced mix improves holdout net return.",
}


def agent(model, instructions, evidence, schema):
    response = ollama("/api/chat", {
        "model": model, "stream": False, "think": False, "format": schema,
        "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 450},
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(evidence, allow_nan=False)},
        ],
    })
    try:
        result = json.loads(response["message"]["content"])
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, TypeError, KeyError):
        raise ValueError("The local model did not return a structured research response.") from None


def validate_weights(weights):
    if not isinstance(weights, dict) or set(weights) != set(WEIGHTS):
        raise ValueError("A challenger must define every monthly factor weight.")
    if (
        any(type(value) is not int for value in weights.values())
        or sum(weights.values()) != 100
        or any(not 0 <= weights[key] <= 45 for key in weights)
        or any(weights[key] < 10 for key in ("quality", "momentum", "volatility"))
        or weights == WEIGHTS
    ):
        raise ValueError("Challenger weights must total 100, vary from baseline, and keep quality, momentum and low volatility at 10–45 points.")
    return weights


def normalize_preferences(preferences, tilt):
    if not isinstance(preferences, dict) or set(preferences) != set(WEIGHTS) or any(
        type(value) is not int or not 0 <= value <= 100 for value in preferences.values()
    ) or not any(preferences.values()):
        raise ValueError("The proposer did not return valid relative factor preferences.")
    core = ("quality", "momentum", "volatility")
    already_valid = (
        sum(preferences.values()) == 100 and max(preferences.values()) <= 45
        and all(preferences[key] >= 10 for key in core)
    )
    if already_valid:
        weights = preferences.copy()
    else:
        minimum = {key: 10 if key in core else 0 for key in WEIGHTS}
        weights = minimum.copy()
        relative = {key: max(0, value - minimum[key]) for key, value in preferences.items()}
        if not any(relative.values()):
            relative = preferences
        for _ in range(100 - sum(weights.values())):
            selected = max(
                (key for key in WEIGHTS if weights[key] < 45),
                key=lambda key: relative[key] / (weights[key] - minimum[key] + 1),
            )
            weights[selected] += 1
    if weights == WEIGHTS:
        receiver = tilt if tilt in core else min(weights, key=weights.get)
        donor = max((key for key in weights if key != receiver), key=weights.get)
        weights[receiver] += 1
        weights[donor] -= 1
    return validate_weights(weights)


def build_research_strategy(model, objective):
    from .data.nse_market import load_nifty100
    from .full_catalogue import readiness, run_report

    frame, market = load_nifty100()
    coverage, records = readiness(frame, market)
    availability_counts = {
        "Complete": coverage["complete"], "Incomplete": coverage["total"] - coverage["complete"],
    }
    observed = {
        item["key"]: [item["available"], item["expected"]]
        for item in coverage["parameters"]
    }
    analytical_inputs = ("debt_equity_ratio", "interest_coverage", "pe_ratio_vs_sector",
                         "promoter_holding_pct", "promoter_pledging_pct", "price_momentum_weekly")
    medians = {
        key: round(median(row["value"] for row in records[key].values()), 3)
        for key in analytical_inputs if records[key]
    }
    evidence = {
        "universe": "Nifty 100", "frequency": "monthly",
        "baseline": WEIGHTS, "candidate_factors": DIMENSIONS, "catalogue_status": availability_counts,
        "historical_coverage": "The builder has no verified point-in-time holdout bundle.",
        "current_evidence": {"as_of": coverage["market"]["asOf"], "observed_required_counts": observed, "observed_medians": medians},
        "objective": objective,
    }
    proposal = agent(
        model,
        "You propose a testable long-only monthly Nifty 100 factor challenger, not stock orders. "
        "Keep every factor named in the baseline. Provide relative integer weight preferences. The app normalizes them to 100 points. "
        "Use values from 0 to 45. The final core weights each need at least 10. "
        "Use current evidence to frame a test hypothesis. Incomplete observations cannot establish a universe-wide finding. "
        "Change at least one weight. Return only the weights and one hypothesis category. No promised returns.",
        evidence,
        {**OBJECTS, "required": ["weights", "tilt"], "properties": {
            "tilt": {"type": "string", "enum": list(TILTS)},
            "weights": {**OBJECTS, "required": list(WEIGHTS), "properties": {
                key: {"type": "integer", "minimum": 10 if key in ("quality", "momentum", "volatility") else 0, "maximum": 45}
                for key in WEIGHTS
            }},
        }},
    )
    tilt = proposal.get("tilt")
    if not isinstance(tilt, str) or tilt not in TILTS:
        raise ValueError("The proposer did not select a supported hypothesis.")
    weights = normalize_preferences(proposal.get("weights"), tilt)
    if tilt in ("quality", "momentum", "volatility") and weights[tilt] <= WEIGHTS[tilt]:
        tilt = "balanced"

    review = agent(
        model,
        "Review this candidate as a skeptical research reviewer. Pick two to four distinct material risks "
        "from risk_codes. Historical coverage is unverified. Do not claim results or approve deployment.",
        {"candidate": weights, "evidence": evidence, "risk_codes": RISKS},
        {**OBJECTS, "required": ["risks"], "properties": {
            "risks": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string", "enum": list(RISKS)}},
        }},
    )
    codes = review.get("risks")
    if not isinstance(codes, list) or not 2 <= len(codes) <= 4 or any(not isinstance(code, str) or code not in RISKS for code in codes):
        raise ValueError("The reviewer did not return supported risk checks.")
    # Feed coverage and data timing are mandatory even if the reviewer omits them.
    flags = list(dict.fromkeys(["data_coverage", "point_in_time", *codes]))
    return {
        "kind": "monthly_challenger", "schema_version": 1, "status": "research_only",
        "created_at": datetime.now(timezone.utc).isoformat(), "model": model, "objective": objective,
        "hypothesis": TILTS[tilt], "weights": weights, "baseline_weights": WEIGHTS,
        "catalogue_status": availability_counts, "evidence_as_of": coverage["market"]["asOf"],
        "source_feeds": coverage["sourceFeeds"],
        "parameterRunReport": run_report(coverage, records, "monthly"), "risks": [RISKS[code] for code in flags],
        "blockers": [
            "Supply a point-in-time monthly dataset and freeze an unseen evaluation period.",
            "Compare net CAGR, rolling returns and drawdown to the fixed monthly baseline and Nifty 100 TRI.",
            "Use research proposals for testing. Gate G1 and existing trading permissions are unchanged.",
        ],
    }


def read_challenger(path):
    return challenger_weights(json.loads(path.read_text(encoding="utf-8-sig")))


def challenger_weights(candidate):
    if (
        not isinstance(candidate, dict)
        or candidate.get("kind") != "monthly_challenger"
        or candidate.get("schema_version") != 1
    ):
        raise ValueError("Supply an exported monthly strategy proposal.")
    return validate_weights(candidate.get("weights"))
