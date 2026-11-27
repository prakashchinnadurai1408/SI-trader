"""Black-Scholes option pricing and Greeks (dependency-free, math only).

Implements:
- European call/put pricing
- Delta, Gamma, Theta, Vega, Rho
- Implied volatility via bisection
- Option chain payoff calculation

All prices in the same currency as the spot. Rates and vol as decimals
(e.g. 0.05 = 5%, 0.20 = 20%). Time-to-expiry in years.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass
class OptionGreeks:
    """Black-Scholes Greeks for a single option."""
    option_type: str        # "call" or "put"
    spot: float
    strike: float
    rate: float             # risk-free rate (decimal, per year)
    vol: float              # implied/historical volatility (decimal, per year)
    tte: float              # time to expiry in years
    price: float            # theoretical option price
    delta: float
    gamma: float
    theta: float            # per year; divide by 365 for per-day
    vega: float             # per 1.0 (100%) vol change; divide by 100 for 1% vol
    rho: float              # per 1.0 rate change; divide by 100 for 1% rate
    d1: float
    d2: float


def black_scholes(
    option_type: str,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    tte: float,
    dividend_yield: float = 0.0,
) -> OptionGreeks:
    """Compute Black-Scholes price and Greeks for a European option.

    Args:
        option_type: "call" or "put".
        spot: Current underlying price (S).
        strike: Strike price (K).
        rate: Risk-free interest rate (decimal, e.g. 0.06 for 6%).
        vol: Volatility (decimal, e.g. 0.25 for 25%).
        tte: Time to expiry in years (e.g. 30/365 for 30 days).
        dividend_yield: Continuous dividend yield (decimal).

    Returns:
        OptionGreeks with price and all Greeks.
    """
    if tte <= 0:
        # At expiry: intrinsic value only.
        if option_type == "call":
            price = max(spot - strike, 0.0)
        else:
            price = max(strike - spot, 0.0)
        return OptionGreeks(
            option_type=option_type, spot=spot, strike=strike,
            rate=rate, vol=vol, tte=tte, price=price,
            delta=1.0 if (option_type == "call" and spot > strike) else 0.0,
            gamma=0.0, theta=0.0, vega=0.0, rho=0.0,
            d1=0.0, d2=0.0,
        )

    if vol <= 0:
        # No vol => deterministic growth at risk-free rate.
        disc = math.exp(-rate * tte)
        fwd = spot * math.exp((rate - dividend_yield) * tte)
        if option_type == "call":
            price = max(fwd - strike * disc, 0.0)  # simplified
        else:
            price = max(strike * disc - fwd, 0.0)
        return OptionGreeks(
            option_type=option_type, spot=spot, strike=strike,
            rate=rate, vol=vol, tte=tte, price=price,
            delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0,
            d1=0.0, d2=0.0,
        )

    sqrt_tte = math.sqrt(tte)
    d1 = (math.log(spot / strike) +
          (rate - dividend_yield + 0.5 * vol * vol) * tte) / (vol * sqrt_tte)
    d2 = d1 - vol * sqrt_tte

    disc = math.exp(-rate * tte)
    div_disc = math.exp(-dividend_yield * tte)

    if option_type == "call":
        price = (spot * div_disc * _norm_cdf(d1)
                 - strike * disc * _norm_cdf(d2))
        delta = div_disc * _norm_cdf(d1)
        rho = strike * tte * disc * _norm_cdf(d2)
    else:
        price = (strike * disc * _norm_cdf(-d2)
                 - spot * div_disc * _norm_cdf(-d1))
        delta = div_disc * (_norm_cdf(d1) - 1.0)
        rho = -strike * tte * disc * _norm_cdf(-d2)

    gamma = (div_disc * _norm_pdf(d1)) / (spot * vol * sqrt_tte)
    theta = (-(spot * div_disc * _norm_pdf(d1) * vol) / (2.0 * sqrt_tte)
             - rate * strike * disc * (_norm_cdf(d2) if option_type == "call" else _norm_cdf(-d2))
             + dividend_yield * spot * div_disc * (_norm_cdf(d1) if option_type == "call" else _norm_cdf(-d1)))
    vega = spot * div_disc * _norm_pdf(d1) * sqrt_tte

    return OptionGreeks(
        option_type=option_type, spot=spot, strike=strike,
        rate=rate, vol=vol, tte=tte, price=round(price, 4),
        delta=round(delta, 4), gamma=round(gamma, 6),
        theta=round(theta, 4), vega=round(vega, 4),
        rho=round(rho, 4), d1=round(d1, 4), d2=round(d2, 4),
    )


def implied_volatility(
    option_type: str,
    spot: float,
    strike: float,
    rate: float,
    market_price: float,
    tte: float,
    dividend_yield: float = 0.0,
    tolerance: float = 1e-6,
    max_iterations: int = 100,
) -> Optional[float]:
    """Implied volatility via bisection. Returns None if not found."""
    if tte <= 0:
        return None
    lo, hi = 1e-6, 5.0  # 0.0001% to 500%
    for _ in range(max_iterations):
        mid = (lo + hi) / 2.0
        price = black_scholes(
            option_type, spot, strike, rate, mid, tte, dividend_yield
        ).price
        if abs(price - market_price) < tolerance:
            return mid
        if price > market_price:
            hi = mid
        else:
            lo = mid
    return None


@dataclass
class OptionChainLink:
    """A single option contract in a chain."""
    symbol: str
    strike: float
    expiry: str
    option_type: str   # "call" or "put"
    spot: float
    rate: float
    vol: float
    tte: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    oi: Optional[int] = None
    volume: Optional[int] = None
    greeks: Optional[OptionGreeks] = None
    iv: Optional[float] = None
    intrinsic_value: float = 0.0
    time_value: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "symbol": self.symbol, "strike": self.strike,
            "expiry": self.expiry, "option_type": self.option_type,
            "spot": self.spot, "rate": self.rate, "vol": self.vol,
            "tte": self.tte,
            "bid": self.bid, "ask": self.ask, "last": self.last,
            "oi": self.oi, "volume": self.volume,
            "intrinsic_value": round(self.intrinsic_value, 4),
            "time_value": round(self.time_value, 4),
        }
        if self.greeks is not None:
            g = self.greeks
            d["greeks"] = {
                "price": g.price, "delta": g.delta, "gamma": g.gamma,
                "theta": g.theta, "vega": g.vega, "rho": g.rho,
                "d1": g.d1, "d2": g.d2,
            }
        if self.iv is not None:
            d["implied_volatility"] = round(self.iv, 6)
        return d


def build_option_chain(
    symbol: str,
    spot: float,
    strikes: List[float],
    expiry: str,
    rate: float,
    vol: float,
    tte: float,
    dividend_yield: float = 0.0,
    market_prices: Optional[Dict[str, Dict[float, float]]] = None,
) -> Dict[str, Any]:
    """Build a full option chain (calls + puts) across strikes.

    Args:
        market_prices: {"call": {strike: price}, "put": {strike: price}}
            observed market prices for IV calculation.
    """
    market_prices = market_prices or {}
    call_prices = market_prices.get("call", {})
    put_prices = market_prices.get("put", {})

    calls: List[Dict[str, Any]] = []
    puts: List[Dict[str, Any]] = []

    for strike in strikes:
        for opt_type, prices, target in (
            ("call", call_prices, calls),
            ("put", put_prices, puts),
        ):
            g = black_scholes(opt_type, spot, strike, rate, vol, tte, dividend_yield)
            mp = prices.get(strike)
            iv = None
            if mp is not None and mp > 0:
                iv = implied_volatility(opt_type, spot, strike, rate, mp, tte, dividend_yield)
            intrinsic = max(spot - strike, 0.0) if opt_type == "call" else max(strike - spot, 0.0)
            link = OptionChainLink(
                symbol=symbol, strike=strike, expiry=expiry,
                option_type=opt_type, spot=spot, rate=rate, vol=vol, tte=tte,
                last=mp, greeks=g, iv=iv,
                intrinsic_value=intrinsic,
                time_value=max((mp if mp is not None else g.price) - intrinsic, 0.0),
            )
            target.append(link.to_dict())

    atm_strike = min(strikes, key=lambda s: abs(s - spot))
    return {
        "symbol": symbol, "spot": spot, "expiry": expiry,
        "rate": rate, "vol": vol, "tte": tte,
        "atm_strike": atm_strike,
        "calls": calls,
        "puts": puts,
        "num_strikes": len(strikes),
    }


def payoff(
    option_type: str,
    strike: float,
    premium: float,
    spot_range: List[float],
) -> List[Dict[str, float]]:
    """Option payoff across a spot range (long position)."""
    results = []
    for s in spot_range:
        if option_type == "call":
            intrinsic = max(s - strike, 0.0)
        else:
            intrinsic = max(strike - s, 0.0)
        pnl = intrinsic - premium
        results.append({
            "spot": round(s, 2),
            "intrinsic": round(intrinsic, 2),
            "premium": round(premium, 2),
            "pnl": round(pnl, 2),
        })
    return results


__all__ = [
    "OptionGreeks", "OptionChainLink",
    "black_scholes", "implied_volatility",
    "build_option_chain", "payoff",
]
