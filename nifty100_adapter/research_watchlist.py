"""Rank a Nifty 100 research watchlist using connected catalogue inputs."""

from .ai_parameters import PARAMETERS, availability
from .data.nse_market import load_nifty100
from .strategy_builder import agent

DAILY = "price_momentum_daily"
WEEKLY = "price_momentum_weekly"
SCREEN = {"liquidity_floor", DAILY, WEEKLY}


def watchlist_catalogue(weights):
    return [
        {
            "key": key, "label": parameter.display_name, "requested": True,
            "role": parameter.role_type.value, "source": parameter.source, "refresh": parameter.refresh_schedule,
            "weight": weights.get(key),
            "status": (
                "Used in ranking" if key in weights else "Used as liquidity filter" if key in SCREEN
                else "Feed pending" if availability(key) == "Feed pending" else "Execution estimate only"
            ),
        }
        for key, parameter in PARAMETERS.items()
    ]


def build_watchlist(model, objective):
    frame, market = load_nifty100()
    threshold = PARAMETERS["liquidity_floor"].min_value
    candidates = frame.loc[frame["daily_turnover_crore"].ge(threshold)].dropna(subset=[DAILY, WEEKLY]).copy()
    choice = agent(model, (
        "Choose factor weights for a Nifty 100 research watchlist. The only ranking inputs available "
        "are daily momentum and five-session momentum. Liquidity is a prefilter. Choose daily_weight "
        "as an integer from 10 to 90; its complement is the five-session weight. Use the strategy "
        "objective to choose the balance. Do not recommend trades, predict returns or infer unavailable facts."
    ), {
        "objective": objective, "available_inputs": ["daily momentum", "five-session momentum", "reported daily turnover"],
        "decision_date": market["asOf"], "covered": market["covered"],
        "pending_risk_checks": market["unverifiedChecks"],
    }, {
        "type": "object", "additionalProperties": False, "required": ["daily_weight"],
        "properties": {"daily_weight": {"type": "integer", "minimum": 10, "maximum": 90}},
    })
    daily_weight = choice.get("daily_weight")
    if type(daily_weight) is not int or not 10 <= daily_weight <= 90:
        raise ValueError("Ollama did not return a valid momentum allocation.")
    weights = {DAILY: daily_weight, WEEKLY: 100 - daily_weight}
    ranks = candidates[list(weights)].rank(pct=True)
    candidates["score"] = (ranks[DAILY] * weights[DAILY] + ranks[WEEKLY] * weights[WEEKLY]).round(4)
    ranked = candidates.sort_values(["score", WEEKLY, "symbol"], ascending=[False, False, True]).head(10)
    rows = [{
        "symbol": item.symbol, "company": item.company_name, "close": round(item.close, 2),
        "daily_change_pct": round(getattr(item, DAILY), 2),
        "five_session_change_pct": round(getattr(item, WEEKLY), 2),
        "turnover_crore": round(item.daily_turnover_crore, 2), "score": round(item.score, 2),
    } for item in ranked.itertuples()]
    return {
        "status": "research_only", "model": model, "market": market, "stocks": rows,
        "market_screen_count": len(candidates), "parameters": watchlist_catalogue(weights),
        "trade_eligible": False,
    }
