"""Indian Cost & Tax Model for SI-Trader.

Implements BRD Section 14 cost model:
- STT (Securities Transaction Tax): 0.1% both buy and sell sides
- STCG (Short-Term Capital Gains) Tax: 20%
- Brokerage: 0.05% per order
- GST on brokerage: 18%
- Roundtrip cost: ~0.38%

All calculations for delivery (CNC) trades.
"""

from dataclasses import dataclass


@dataclass
class IndianCostModel:
    """Indian market cost and tax parameters."""
    stt_rate_equity: float = 0.001    # 0.1% STT per side
    stt_rate_derivative: float = 0.0001  # 0.01% for derivatives
    stcg_tax_rate: float = 0.20       # 20% STCG
    brokerage_rate: float = 0.0005    # 0.05% brokerage
    gst_rate: float = 0.18            # 18% GST on brokerage
    dp_charge_sell: float = 13.50     # DP charge on sell
    sebi_turnover_fee: float = 0.000001  # SEBI turnover fee
    stamp_duty: float = 0.00003       # 0.003% stamp duty (buy side)

    @property
    def roundtrip_cost_pct(self) -> float:
        """Estimated roundtrip cost percentage."""
        return (self.stt_rate_equity * 2 + 
                self.brokerage_rate * 2 * (1 + self.gst_rate) +
                self.sebi_turnover_fee * 2 +
                self.stamp_duty) * 100

    def calculate_buy_costs(self, price: float, quantity: int) -> Dict[str, float]:
        """Calculate buy-side costs."""
        stt = self.stt_rate_equity * price * quantity
        brokerage = self.brokerage_rate * price * quantity
        gst = brokerage * self.gst_rate
        sebi = self.sebi_turnover_fee * price * quantity
        stamp = self.stamp_duty * price * quantity
        return {
            "stt": stt,
            "brokerage": brokerage,
            "gst": gst,
            "sebi": sebi,
            "stamp_duty": stamp,
            "total": stt + brokerage + gst + sebi + stamp,
        }

    def calculate_sell_costs(self, price: float, quantity: int) -> Dict[str, float]:
        """Calculate sell-side costs."""
        stt = self.stt_rate_equity * price * quantity
        brokerage = self.brokerage_rate * price * quantity
        gst = brokerage * self.gst_rate
        sebi = self.sebi_turnover_fee * price * quantity
        dp = self.dp_charge_sell
        return {
            "stt": stt,
            "brokerage": brokerage,
            "gst": gst,
            "sebi": sebi,
            "dp_charge": dp,
            "total": stt + brokerage + gst + sebi + dp,
        }

    def calculate_net_pnl(self,
                          buy_price: float,
                          sell_price: float,
                          quantity: int) -> Dict[str, float]:
        """Calculate net P&L after all costs and STCG tax.
        
        Returns dict with gross_pnl, total_costs, net_before_tax,
        stcg_tax, net_after_tax.
        """
        gross_pnl = (sell_price - buy_price) * quantity
        
        buy_costs = self.calculate_buy_costs(buy_price, quantity)
        sell_costs = self.calculate_sell_costs(sell_price, quantity)
        total_costs = buy_costs["total"] + sell_costs["total"]
        
        net_before_tax = gross_pnl - total_costs
        
        # STCG tax on profit only
        if net_before_tax > 0:
            stcg_tax = net_before_tax * self.stcg_tax_rate
        else:
            stcg_tax = 0.0
        
        net_after_tax = net_before_tax - stcg_tax
        
        return {
            "gross_pnl": gross_pnl,
            "buy_costs": buy_costs["total"],
            "sell_costs": sell_costs["total"],
            "total_costs": total_costs,
            "net_before_tax": net_before_tax,
            "stcg_tax": stcg_tax,
            "net_after_tax": net_after_tax,
            "net_return_pct": (net_after_tax / (buy_price * quantity)) * 100 if buy_price > 0 else 0,
        }


# Module-level instance
_cost_model_instance: Optional[IndianCostModel] = None


def get_cost_model() -> IndianCostModel:
    """Get singleton cost model instance."""
    global _cost_model_instance
    if _cost_model_instance is None:
        _cost_model_instance = IndianCostModel()
    return _cost_model_instance


__all__ = [
    "IndianCostModel",
    "get_cost_model",
]


# Optional typing import for type hints
from typing import Optional, Dict