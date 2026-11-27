"""Explicitly hypothetical option sensitivities and Monte Carlo scenarios."""
import math
import numpy as np


def greeks(spot, strike, years, volatility, rate, dividend=0, option="call"):
    values = (spot, strike, years, volatility, rate, dividend)
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("Greek inputs must be finite numbers.")
    if min(spot, strike, years, volatility) <= 0 or max(spot, strike)>1e9 or years > 10 or volatility > 5 or not -1 <= rate <= 1 or not 0 <= dividend <= 1 or option not in ("call", "put"):
        raise ValueError("Use positive spot, strike, maturity and volatility, and call or put.")
    root = math.sqrt(years)
    d1 = (math.log(spot/strike)+(rate-dividend+.5*volatility**2)*years)/(volatility*root)
    d2 = d1-volatility*root
    cdf = lambda value: .5*(1+math.erf(value/math.sqrt(2)))
    pdf = math.exp(-.5*d1*d1)/math.sqrt(2*math.pi)
    dq, dr = math.exp(-dividend*years), math.exp(-rate*years)
    sign = 1 if option == "call" else -1
    price = sign*(spot*dq*cdf(sign*d1)-strike*dr*cdf(sign*d2))
    theta = -spot*dq*pdf*volatility/(2*root)-sign*rate*strike*dr*cdf(sign*d2)+sign*dividend*spot*dq*cdf(sign*d1)
    return {"theoreticalPrice": price, "delta": sign*dq*cdf(sign*d1),
            "gamma": dq*pdf/(spot*volatility*root), "vegaPerVolPoint": spot*dq*pdf*root/100,
            "thetaPerCalendarDay": theta/365, "rhoPerRatePoint": sign*strike*years*dr*cdf(sign*d2)/100}


def scenario(payload):
    def number(key, default=None):
        value = payload.get(key, default)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Provide finite numeric scenario assumptions.")
        return value
    spot, strike = number("spot"), number("strike")
    vol, rate, dividend = number("volatilityPct")/100, number("ratePct", 0)/100, number("dividendPct", 0)/100
    days, horizon = number("calendarDays", 30), number("sessions", 21)
    if not 1 <= days <= 3650 or type(horizon) is not int or not 1 <= horizon <= 252 or not -1 <= rate <= 1 or not 0 <= dividend <= 1:
        raise ValueError("Use 1–252 trading sessions and valid maturity, rate and dividend assumptions.")
    sensitivities = greeks(spot, strike, days/365, vol, rate, dividend, payload.get("option", "call"))
    # Zero expected arithmetic price drift: log increment includes -0.5 sigma^2.
    shocks = np.random.default_rng(42).standard_normal((10000, horizon))
    terminal = np.expm1((-.5*vol**2/252 + vol/math.sqrt(252)*shocks).sum(axis=1))*100
    quantiles = np.percentile(terminal, [5, 25, 50, 75, 95])
    tail = terminal[terminal <= quantiles[0]]
    return {"kind": "hypothetical_scenario", "greeks": sensitivities,
            "monteCarlo": {"paths": 10000, "sessions": horizon, "seed": 42,
                "percentiles": [5,25,50,75,95], "terminalReturnsPct": quantiles.tolist(),
                "var95LossPct": max(0., -float(quantiles[0])), "expectedShortfall95LossPct": max(0., -float(tail.mean())),
                "assumption": "GBM, constant supplied volatility, zero arithmetic price drift; no costs, gaps, volatility clustering or calibration"},
            "inputs": payload, "tradeEligible": False,
            "note": "Supplied assumptions, not observed option IV or calibrated return forecasts. Greeks use European Black–Scholes with continuous dividend yield."}
