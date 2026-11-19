"""Read InvestRight account snapshots and estimate cash-sized paper fills."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import math

from .config.indian_cost_model import get_cost_model
from .investright import broker_get

ENDPOINTS = {
    "funds": "/oapi/v1/user/margins",
    "holdings": "/oapi/v1/portfolio/holdings",
    "positions": "/oapi/v1/portfolio/cumulative-positions",
    "orders": "/oapi/v1/orders",
    "trades": "/oapi/v1/trades",
}
PENNY = Decimal("0.01")


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(",", ""))
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def cash_amount(data):
    try:
        cash = number(data["equity"]["totalAvailableLimitDetails"]["cash"])
    except (KeyError, TypeError):
        cash = None
    if cash is None or cash < 0:
        raise ValueError("InvestRight did not report a separate cash balance.")
    return cash


def contains_records(data, account_section):
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        key = {"positions": "net", "orders": "orders", "trades": "trades"}.get(account_section)
        rows = data.get(key)
    else:
        rows = None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("InvestRight returned an unexpected response format.")
    fields = {
        "holdings": ("company_name", "security_id", "exchange", "isin", "quantity", "average_price", "close_price"),
        "positions": ("company_name", "underlying_symbol", "security_id", "exchange", "product", "net_qty", "average_buy_price", "realised_pl_overall_position"),
        "orders": ("company_name", "underlying_symbol", "security_id", "transaction_type", "quantity", "filled_quantity", "average_price", "status", "order_timestamp"),
        "trades": ("company_name", "underlying_symbol", "security_id", "transaction_type", "quantity", "filled_quantity", "trade_quantity", "traded_quantity", "average_price", "trade_price", "traded_price", "trade_timestamp", "order_timestamp"),
    }[account_section]
    return [{key: row[key] for key in fields if key in row} for row in rows]


def broker_snapshot():
    def fetch(section):
        try:
            data = broker_get(ENDPOINTS[section])
            value = cash_amount(data) if section == "funds" else contains_records(data, section)
            return section, {"value": value}
        except (ValueError, OSError) as error:
            return section, {"error": str(error)}

    with ThreadPoolExecutor(max_workers=3) as executor:
        snapshot = dict(executor.map(fetch, ENDPOINTS))
    snapshot["asOf"] = datetime.now(timezone.utc).isoformat()
    return snapshot


def entry_cost_terms():
    cost = get_cost_model()
    variable = Decimal(str(cost.total_buy_cost_pct + cost.exchange_tax + cost.sebi_charge + cost.estimated_slippage))
    fixed = Decimal(str(max(0, cost.brokerage_min) * (1 + cost.gst_on_brokerage)))
    return variable, fixed


def affordable_candidates(candidates, budget, cash_buffer):
    if budget < 0.01:
        return []
    variable, fixed = entry_cost_terms()
    available = Decimal(str(budget)).quantize(PENNY, rounding=ROUND_FLOOR)
    result = []
    for stock in candidates:
        entry = (Decimal(str(stock["price"])) * (1 + variable) + fixed).quantize(PENNY, rounding=ROUND_CEILING)
        minimum_weight = (entry / available * 100).quantize(PENNY, rounding=ROUND_CEILING)
        if minimum_weight <= min(20, 100 - cash_buffer):
            result.append({**stock, "minimumWeight": float(minimum_weight)})
    return result


def paper_sizing(basket, budget, cash_buffer, scenario_move, execute):
    cost = get_cost_model()
    variable, fixed = entry_cost_terms()
    capital = Decimal(str(budget)).quantize(PENNY, rounding=ROUND_FLOOR)
    max_spend = (capital * (1 - Decimal(str(cash_buffer)) / 100)).quantize(PENNY, rounding=ROUND_FLOOR)
    remaining = max_spend
    results = []
    fills = []
    for stock in basket:
        price = Decimal(str(stock["price"]))
        cap = min(remaining, (capital * Decimal(str(stock["weight"])) / 100).quantize(PENNY, rounding=ROUND_FLOOR))
        quantity = max(0, int(((cap - fixed) / (price * (1 + variable))).to_integral_value(rounding=ROUND_FLOOR)))
        debit = (price * quantity * (1 + variable) + fixed).quantize(PENNY, rounding=ROUND_CEILING) if quantity else Decimal(0)
        market_value = price * quantity
        remaining -= debit
        pnl = []
        for move in (-scenario_move, 0, scenario_move):
            buy = float(price)
            sell = buy * (1 + move / 100)
            scenario = cost.calculate_net_pnl(buy, sell, quantity)
            extra = (buy + sell) * quantity * (cost.estimated_slippage + cost.exchange_tax + cost.sebi_charge)
            pnl.append(round(scenario["net_after_tax"] - extra, 2) if quantity else 0)
        results.append({
            **stock, "quantity": quantity, "entryValue": round(float(market_value), 2),
            "cashRequired": float(debit), "scenarioPnl": pnl,
            "scenarioRoi": [round(value / float(debit) * 100, 2) if debit else None for value in pnl],
        })
        if execute and quantity:
            fills.append({
                "symbol": stock["symbol"], "quantity": quantity, "price": float(price),
                "cashRequired": float(debit), "status": "Simulated buy",
            })
    spent = max_spend - remaining
    totals = [round(sum(item["scenarioPnl"][index] for item in results), 2) for index in range(3)]
    return {
        "basket": results, "fills": fills, "budget": float(capital), "allocated": float(spent),
        "cashRemaining": float(capital - spent), "scenarioMove": scenario_move, "scenarioPnl": totals,
        "scenarioRoi": [round(value / float(spent) * 100, 2) if spent else None for value in totals],
        "asOf": datetime.now(timezone.utc).isoformat(),
    }
