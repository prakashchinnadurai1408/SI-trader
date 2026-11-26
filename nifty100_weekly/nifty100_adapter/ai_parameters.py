"""AI proposals for the paper strategy parameter catalogue."""

from dataclasses import replace
import json

from .ai_strategy import ollama
from .config.parameter_catalogue import PARAMETER_CATALOGUE, RoleType

PARAMETERS = {item.parameter_key: item for item in PARAMETER_CATALOGUE.values()}
ROLES = [role.value for role in RoleType]
SCHEDULES = ("daily", "weekly", "monthly", "quarterly", "yearly", "annually", "on-event", "per_trade", "fy_update")
PROTECTED = {
    "liquidity_floor", "cost_vs_edge_check", "asm_gsm_surveillance",
    "promoter_pledging_pct", "legal_cases_directors", "legal_cases_company_promoters", "regulatory_actions",
    "stt_rate_equity", "stcg_tax_rate", "brokerage_rate",
}
LIVE_COLUMNS = {"price_momentum_daily", "price_momentum_weekly"}.intersection(PARAMETERS)
COST_INPUTS = {"stt_rate_equity", "stcg_tax_rate", "brokerage_rate"}


def availability(key):
    if key in LIVE_COLUMNS or key == "liquidity_floor":
        return "NSE data"
    if key == "cost_vs_edge_check":
        return "Calculated"
    if key in COST_INPUTS:
        return "Model estimate"
    return "Feed pending"


def validate_profile(profile):
    if not isinstance(profile, list) or len(profile) != len(PARAMETERS):
        raise ValueError("Generate a complete AI parameter catalogue in Strategy configuration.")
    indexed = {}
    for item in profile:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            raise ValueError("Invalid parameter catalogue.")
        key = item["key"]
        definition = PARAMETERS.get(key)
        if not definition or key in indexed:
            raise ValueError("Catalogue contains an unknown or duplicate parameter.")
        enabled, role, weight, source, refresh = (
            item.get(field) for field in ("enabled", "role", "weight", "source", "refresh")
        )
        if (
            type(enabled) is not bool or role not in ROLES or type(weight) is not int
            or not (1 <= weight <= 25 if enabled else weight == 0)
            or source != definition.source or refresh not in SCHEDULES
        ):
            raise ValueError("Catalogue contains an invalid role, weight, source or refresh schedule.")
        if key in PROTECTED and (not enabled or role != definition.role_type.value):
            raise ValueError("The catalogue must preserve protected checks.")
        if key in LIVE_COLUMNS and enabled and role not in ("Score", "Advisory", "Flag"):
            raise ValueError("Price momentum supports Score, Advisory or Flag in this build.")
        indexed[key] = item
    if sum(item["weight"] for item in indexed.values()) != 100:
        raise ValueError("Enabled weights must total 100.")
    if not any(indexed[key]["enabled"] and indexed[key]["role"] == "Score" for key in LIVE_COLUMNS):
        raise ValueError("Enable at least one connected momentum score.")
    return indexed


def score_parameters(indexed):
    return [
        replace(PARAMETERS[key], weight=item["weight"], role_type=RoleType.SCORE, min_value=0)
        for key, item in indexed.items()
        if item["enabled"] and item["role"] == "Score" and key in LIVE_COLUMNS
    ]


def propose_profile(model, objective):
    keys = list(PARAMETERS)
    inputs = [
        [index, item.display_name, item.role_type.value, item.refresh_schedule, availability(key)]
        for index, (key, item) in enumerate(PARAMETERS.items())
    ]
    response = ollama("/api/chat", {
        "model": model, "stream": False, "think": False,
        "format": {
            "type": "object", "required": ["momentum", "enabled"], "additionalProperties": False,
            "properties": {
                "momentum": {"type": "string", "enum": ["daily", "weekly", "both"] if "price_momentum_daily" in LIVE_COLUMNS else ["weekly"]},
                "enabled": {
                    "type": "array", "maxItems": 12,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["id", "role", "weight", "refresh"],
                        "properties": {
                            "id": {"type": "integer"},
                            "role": {"type": "string", "enum": ROLES},
                            "weight": {"type": "integer"},
                            "refresh": {"type": "string", "enum": list(SCHEDULES)},
                        },
                    },
                },
            },
        },
        "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 800},
        "messages": [
            {"role": "system", "content": (
                "Configure a Nifty 100 paper strategy parameter catalogue for the objective. "
                "Input rows are [id,name,default role,default refresh,data status]. "
                "Set momentum to daily, weekly, or both, and return enabled objects with id, role, weight, and refresh. "
                "Select up to 8 relevant rows and omit disabled rows. Use the momentum selection to designate "
                "connected scores. Feed-pending rows may be useful for future "
                "screening; their configured intent does not imply available data. "
                "Keep Filter/Veto roles for safety checks. Weights are integers 1 to 25. "
                "Choose refresh by name from the supplied schedule list."
            )},
            {"role": "user", "content": json.dumps({
                "objective": objective, "roles": ROLES, "schedules": SCHEDULES, "catalogue": inputs,
            })},
        ],
    })
    try:
        proposal = json.loads(response["message"]["content"])
        proposals = proposal["enabled"]
        momentum = proposal["momentum"]
        if not isinstance(proposals, list) or len(proposals) > 12 or momentum not in ("daily", "weekly", "both"):
            raise ValueError()
        choices = {}
        for row in proposals:
            index, role, weight, schedule = (row[field] for field in ("id", "role", "weight", "refresh"))
            if type(index) is not int or not 0 <= index < len(keys) or type(weight) is not int:
                continue
            key = keys[index]
            if key not in choices and role in ROLES and schedule in SCHEDULES:
                choices[key] = (role, min(25, max(1, weight)), schedule)
        for key in LIVE_COLUMNS:
            definition = PARAMETERS[key]
            period = key.rsplit("_", 1)[1]
            if momentum in (period, "both"):
                _, weight, schedule = choices.get(key, ("Score", definition.weight, definition.refresh_schedule))
                choices[key] = ("Score", weight, schedule)
            elif key in choices:
                _, weight, schedule = choices[key]
                choices[key] = ("Advisory", weight, schedule)
        for key in PROTECTED:
            definition = PARAMETERS[key]
            _, weight, _ = choices.get(key, ("", max(definition.weight, 4), ""))
            choices[key] = (definition.role_type.value, weight, definition.refresh_schedule)
        weights = {key: 1 for key in keys if key in choices}
        # Allocate remaining points in proportion to the model's preferences,
        # keeping every enabled row between 1 and 25.
        for _ in range(100 - len(weights)):
            key = max((key for key in weights if weights[key] < 25),
                      key=lambda key: choices[key][1] / (weights[key] + 1))
            weights[key] += 1
        profile = []
        for key, definition in PARAMETERS.items():
            role, _, refresh = choices.get(key, (definition.role_type.value, 0, definition.refresh_schedule))
            profile.append({
                "key": key, "enabled": key in choices, "role": role, "weight": weights.get(key, 0),
                "source": definition.source, "refresh": refresh,
            })
        return validate_profile(profile).values()
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError("Ollama returned an invalid catalogue. Try generating it again.") from None


def catalogue_view(profile):
    return [
        {**item, "label": PARAMETERS[item["key"]].display_name,
         "availability": availability(item["key"]), "protected": item["key"] in PROTECTED}
        for item in profile
    ]
