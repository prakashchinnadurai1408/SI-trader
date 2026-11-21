"""Weight-aware strategy backtester for SI-Trader.

The generic Phase1 pipeline backtests a fixed weekly selection rule and
ignores which weights a strategy chose, so two candidate strategies get
identical results. This module instead drives the BRD Section 27.5 pipeline
from the candidate's own parameter weights:

    score(stock, bar) = sum(weight_i * value_i) / sum(weight_i)

Only parameters derivable from price/volume contribute; the rest are
treated as absent rather than neutral, so weights on unavailable data do
not silently inflate the score.

Costing uses the real Indian cost model (STT 0.1% per side, brokerage,
STCG 20%) so every reported number is after cost and tax.

Dependency-free: works on core requirements.txt (numpy/pandas).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import logging

logger = logging.getLogger(__name__)


@dataclass
class StrategyBacktestResult:
    """Backtest metrics for one strategy."""
    strategy_name: str
    bars_used: int = 0
    symbols: List[str] = field(default_factory=list)
    total_return_pct: float = 0.0
    net_profit: float = 0.0
    sharpe: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    avg_trade_pct: float = 0.0
    expectancy: float = 0.0
    final_value: float = 0.0
    cost_pct: float = 0.38
    edge_passes: bool = False
    brd_compliant: bool = False
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "bars_used": self.bars_used,
            "symbols": self.symbols,
            "total_return": self.total_return_pct,
            "net_profit": self.net_profit,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown_pct,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "avg_trade": self.avg_trade_pct,
            "expectancy": self.expectancy,
            "final_value": self.final_value,
            "cost_pct": self.cost_pct,
            "engine": "sitrader-weighted",
        }


class StrategyBacktester:
    """Backtests a strategy's parameter weights over OHLCV history."""

    # Parameters we can actually observe from price/volume each bar.
    PRICE_DERIVED = {
        "price_momentum_daily": 1,
        "price_momentum_weekly": 5,
        "price_momentum_monthly": 21,
        "price_momentum_yearly": 252,
        "midcap_volatility_adj": 21,
        "midcap_liquidity_score": 21,
        "liquidity_floor": 1,
    }

    def __init__(self, cost_model=None, capital: float = 25000.0,
                 top_n: int = 5, min_bars: int = 30):
        if cost_model is None:
            from ..config.indian_cost_model import get_cost_model
            cost_model = get_cost_model()
        self.cost_model = cost_model
        self.capital = capital
        self.top_n = top_n
        self.min_bars = min_bars

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _features(self, bars: Sequence[Dict[str, Any]],
                  end: int) -> Dict[str, float]:
        """Raw feature values observable at bar index `end` (0-based close)."""
        closes = [float(b["close"]) for b in bars[: end + 1]]
        vols = [float(b.get("volume", 0)) for b in bars[: end + 1]]
        n = len(closes)
        if n < 2:
            return {}
        last = closes[-1]
        out: Dict[str, float] = {}

        def mom(lookback: int) -> Optional[float]:
            if n > lookback and closes[-lookback - 1] > 0:
                return (last / closes[-lookback - 1] - 1) * 100
            return None

        for key, lookback in self.PRICE_DERIVED.items():
            if key == "midcap_volatility_adj":
                continue
            if key == "midcap_liquidity_score":
                continue
            if key == "liquidity_floor":
                out[key] = vols[-1] * last
                continue
            value = mom(lookback)
            if value is not None:
                out[key] = value

        # realised volatility over the last 21 bars
        window = closes[-22:]
        rets = [math.log(window[i] / window[i - 1])
                for i in range(1, len(window)) if window[i - 1] > 0]
        if len(rets) > 1:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            out["midcap_volatility_adj"] = math.sqrt(var) * math.sqrt(252) * 100

        # liquidity: 21-day mean turnover in rupees
        window = closes[-21:]
        vwindow = vols[-21:]
        if window:
            out["midcap_liquidity_score"] = (
                sum(v * c for v, c in zip(vwindow, window)) / len(window))
        return out

    def _score(self, weights: Dict[str, int],
               features: Dict[str, float]) -> Optional[float]:
        """Weighted score in 0..1, or None when no weight has data."""
        num = 0.0
        den = 0.0
        for key, weight in weights.items():
            if weight <= 0 or key not in features:
                continue
            value = features[key]
            if key.startswith("price_momentum"):
                norm = max(-100.0, min(100.0, value)) / 200.0 + 0.5
            elif key == "midcap_volatility_adj":
                norm = max(0.0, min(100.0, value)) / 100.0
                norm = 1.0 - norm  # lower volatility scores higher
            else:  # turnover measures
                norm = math.log10(max(value, 1.0)) / 12.0
            num += weight * norm
            den += weight
        if den == 0:
            return None
        return num / den

    # ------------------------------------------------------------------
    # Backtest
    # ------------------------------------------------------------------

    def run(self, strategy_name: str, weights: Dict[str, int],
            prices: Dict[str, Sequence[Dict[str, Any]]]) -> StrategyBacktestResult:
        symbols = [s for s, b in prices.items()
                   if b and len(b) >= self.min_bars]
        result = StrategyBacktestResult(
            strategy_name=strategy_name, symbols=symbols,
            cost_pct=self.cost_model.roundtrip_cost_pct)
        if not symbols:
            result.notes.append("no symbols with enough history")
            return result

        horizon = min(
            (len(prices[s]) for s in symbols)) - 1
        if horizon < self.min_bars:
            result.notes.append("insufficient aligned history")
            return result

        cost = self.cost_model
        returns: List[float] = []
        trade_count = 0
        wins = 0
        gross = 0.0

        for t in range(self.min_bars, horizon):
            ranked = []
            for sym in symbols:
                feats = self._features(prices[sym], t)
                score = self._score(weights, feats)
                if score is not None:
                    ranked.append((score, sym, feats))
            if len(ranked) < 2:
                continue
            ranked.sort(reverse=True)

            for score, sym, _ in ranked[: self.top_n]:
                bars = prices[sym]
                buy = float(bars[t]["close"])
                nxt = bars[t + 1]
                sell = float(nxt["close"])
                if buy <= 0:
                    continue
                # Size the position like the platform does (capital split
                # across the basket) so the flat per-order DP charge is
                # amortised instead of dominating a 1-share trade.
                qty = max(1, int((self.capital / max(self.top_n, 1)) / buy))
                pnl = cost.calculate_net_pnl(buy, sell, qty)
                net_pct = pnl["net_return_pct"]
                returns.append(net_pct)
                gross += pnl["net_after_tax"]
                trade_count += 1
                if pnl["net_after_tax"] > 0:
                    wins += 1
            result.bars_used = t - self.min_bars + 1

        if returns:
            result.total_trades = trade_count
            result.win_rate = (wins / trade_count * 100) if trade_count else 0.0
            result.avg_trade_pct = sum(returns) / len(returns)
            result.expectancy = result.avg_trade_pct * (result.win_rate / 100) - (
                (100 - result.win_rate) / 100) * abs(result.avg_trade_pct)
            result.net_profit = gross
            result.final_value = self.capital + gross
            result.total_return_pct = (
                (result.final_value - self.capital) / self.capital * 100)
            result.sharpe = self._sharpe(returns)
            result.max_drawdown_pct = self._max_drawdown(returns)
            net_edge = result.avg_trade_pct
            result.edge_passes = net_edge > 0.3
            result.brd_compliant = result.edge_passes and result.net_profit > 0
        else:
            result.notes.append("no trades generated")

        return result

    def run_candidate(self, candidate: Any,
                      prices: Dict[str, Sequence[Dict[str, Any]]]
                      ) -> Dict[str, Any]:
        """Backtest a StrategyCandidate using its own weights."""
        weights = getattr(candidate, "parameter_weights", {}) or {}
        result = self.run(getattr(candidate, "name", "candidate"),
                          weights, prices)
        candidate.backtest_results = result.as_dict()
        candidate.edge_validation = {
            "gross_return": result.total_return_pct,
            "cost_pct": result.cost_pct,
            "net_edge": result.avg_trade_pct,
            "min_edge_required": 0.3,
            "edge_passes": result.edge_passes,
            "profitable": result.net_profit > 0,
            "brd_compliant": result.brd_compliant,
        }
        return result.as_dict()

    # ------------------------------------------------------------------
    # Statistics helpers (pure python, no numpy dependency)
    # ------------------------------------------------------------------

    @staticmethod
    def _sharpe(returns: List[float], periods_per_year: int = 52) -> float:
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(var)
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(periods_per_year)

    @staticmethod
    def _max_drawdown(returns: List[float]) -> float:
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in returns:
            equity += r
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)
        return max_dd


def backtest_strategy(weights: Dict[str, int],
                      prices: Dict[str, Sequence[Dict[str, Any]]],
                      strategy_name: str = "strategy",
                      capital: float = 25000.0,
                      top_n: int = 5) -> Dict[str, Any]:
    """Convenience helper: backtest a weight configuration."""
    backtester = StrategyBacktester(capital=capital, top_n=top_n)
    return backtester.run(strategy_name, weights, prices).as_dict()


__all__ = [
    "StrategyBacktester", "StrategyBacktestResult", "backtest_strategy",
]