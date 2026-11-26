"""Indian market cost and tax model for backtesting.

All rates as applicable for FY 2026-27 (assessment year 2027-28).
Rates confirmed with reference to:
- STT on equity delivery: 0.1% on both buy and sell (Sebi notification)
- STCG (Securities Transaction Tax categorized as STCG): 20% for FY 2026-27
- LTCG (long-term > 12 months): 12.5% above ₹1.25 lakh exemption (budget 2024)
- Brokerage: Negotiable, typically ₹20-50 per order or percentage
- Stamp duty: Varies by state, ~0.01% to 0.1% on delivery
- GST: 18% on brokerage
- SEBI turnover charge: negligible for retail (typically 0.0001%)
- Stamp duty on intraday: different rates
- Slippage: estimated 0.05-0.2% depending on liquidity
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class IndianCostModel:
    """Cost and tax parameters for Indian equity delivery trading."""

    # Transaction costs (percentage of turnover)
    stt_buy: float = 0.1 / 100   # 0.1% on buy delivery
    stt_sell: float = 0.1 / 100  # 0.1% on sell delivery

    # Legacy-compatible single STT rate (both sides)
    stt_rate_equity: float = 0.1 / 100  # 0.1% STT per side

    # Brokerage (configurable, default ₹20 per order or 0.05%)
    brokerage_rate: float = 0.05 / 100  # 0.05% as default percentage
    brokerage_min: float = 20.0  # Minimum brokerage per order

    # Exchange charges
    sebi_charge: float = 0.0001 / 100  # SEBI turnover charge
    exchange_tax: float = 0.001 / 100   # Exchange transaction charge

    # Taxes
    stcg_tax_rate: float = 0.20  # 20% short-term capital gains tax
    # LTCG: 12.5% above ₹1.25 lakh exemption (Budget 2024)
    # Not used for weekly delivery (holding < 12 months = STCG)

    # Other costs
    stamp_duty_buy: float = 0.01 / 100  # Stamp duty on buy (varies by state)
    stamp_duty_sell: float = 0.005 / 100  # Stamp duty on sell (varies by state)
    gst_on_brokerage: float = 0.18  # 18% GST on brokerage

    # Estimated slippage (percentage - depends on liquidity)
    estimated_slippage: float = 0.05 / 100  # 0.05% typical for Nifty 100

    # DP charges (per script, fixed)
    dp_charge_sell: float = 10.0  # Typical DP charge on sell

    @property
    def total_buy_cost_pct(self) -> float:
        """Total cost percentage on buy (STT + brokerage + stamp duty + GST)."""
        return (self.stt_buy +
                self.brokerage_rate +
                self.stamp_duty_buy +
                (self.brokerage_rate * self.gst_on_brokerage))

    @property
    def total_sell_cost_pct(self) -> float:
        """Total cost percentage on sell (STT + brokerage + stamp duty + GST + DP + slippage)."""
        return (self.stt_sell +
                self.brokerage_rate +
                self.stamp_duty_sell +
                (self.brokerage_rate * self.gst_on_brokerage) +
                self.dp_charge_sell / 10000 +  # Convert ₹10 to percentage
                self.estimated_slippage)

    @property
    def total_roundtrip_cost_pct(self) -> float:
        """Total cost percentage for a round trip (buy + sell)."""
        return self.total_buy_cost_pct + self.total_sell_cost_pct

    # Legacy-compatible alias for total_roundtrip_cost_pct (returns percent,
    # matching legacy `roundtrip_cost_pct` semantics used by sitrader backtester).
    @property
    def roundtrip_cost_pct(self) -> float:
        """Legacy alias returning roundtrip cost as a percentage value."""
        return self.total_roundtrip_cost_pct * 100

    def calculate_buy_costs(self, price: float, quantity: int) -> Dict[str, float]:
        """Legacy-format buy-side cost breakdown."""
        stt = self.stt_buy * price * quantity
        brokerage = self.brokerage_rate * price * quantity
        gst = brokerage * self.gst_on_brokerage
        sebi = self.sebi_charge * price * quantity
        stamp = self.stamp_duty_buy * price * quantity
        return {
            "stt": stt,
            "brokerage": brokerage,
            "gst": gst,
            "sebi": sebi,
            "stamp_duty": stamp,
            "total": stt + brokerage + gst + sebi + stamp,
        }

    def calculate_sell_costs(self, price: float, quantity: int) -> Dict[str, float]:
        """Legacy-format sell-side cost breakdown."""
        stt = self.stt_sell * price * quantity
        brokerage = self.brokerage_rate * price * quantity
        gst = brokerage * self.gst_on_brokerage
        sebi = self.sebi_charge * price * quantity
        dp = self.dp_charge_sell
        return {
            "stt": stt,
            "brokerage": brokerage,
            "gst": gst,
            "sebi": sebi,
            "dp_charge": dp,
            "total": stt + brokerage + gst + sebi + dp,
        }
    # ------------------------------------------------------------------

    def calculate_stcg(self, buy_price: float, sell_price: float, quantity: int) -> float:
        """Calculate short-term capital gain tax."""
        # Gross P&L
        gross_pnl = (sell_price - buy_price) * quantity

        # Tax on gross P&L (since weekly delivery = < 12 months = STCG)
        if gross_pnl > 0:
            return gross_pnl * self.stcg_tax_rate
        return 0.0

    def calculate_net_pnl(self,
                          buy_price: float,
                          sell_price: float,
                          quantity: int) -> Dict[str, float]:
        """Calculate net P&L after all costs and taxes."""
        # Gross P&L
        gross_pnl = (sell_price - buy_price) * quantity

        # Total brokerage
        buy_brokerage = (buy_price * self.brokerage_rate * quantity +
                        max(self.brokerage_min, 0))
        sell_brokerage = (sell_price * self.brokerage_rate * quantity +
                         max(self.brokerage_min, 0))
        total_brokerage = buy_brokerage + sell_brokerage

        # STT
        stt = (self.stt_buy * buy_price * quantity +
               self.stt_sell * sell_price * quantity)

        # stamp duty
        stamp_duty = (self.stamp_duty_buy * buy_price * quantity +
                     self.stamp_duty_sell * sell_price * quantity)

# GST on brokerage (18% of total brokerage, reverse charge calculation)
        brokerage_gst = (buy_brokerage + sell_brokerage) * 0.18 / 1.18  # reverse charge

        # DP charges (only on sell)
        dp_charges = self.dp_charge_sell  # Fixed ₹10 per script

        # Total costs: STT + brokerage + stamp duty + GST + DP
        total_costs = stt + total_brokerage + stamp_duty + brokerage_gst + dp_charges

        # Net P&L before tax
        net_pnl = gross_pnl - total_costs

        # Pre-tax P&L = gross minus all costs
        pre_tax_pnl = gross_pnl - total_costs

        # STCG tax (20% on positive P&L for weekly holding < 12 months)
        stcg_tax = pre_tax_pnl * self.stcg_tax_rate if pre_tax_pnl > 0 else 0.0
        net_after_tax = pre_tax_pnl - stcg_tax

        return {
            "gross_pnl": gross_pnl,
            "total_costs": total_costs,
            "pre_tax_pnl": pre_tax_pnl,
            "stcg_tax": stcg_tax,
            "net_after_tax": net_after_tax,
            "net_return_pct": (net_after_tax / (buy_price * quantity) * 100) if buy_price > 0 else 0.0,
            "breakdown": {
                "gross_pnl": gross_pnl,
                "stt": stt,
                "brokerage": total_brokerage,
                "stamp_duty": stamp_duty,
                "gst": brokerage_gst,
                "dp_charges": dp_charges
            }
        }


# Default model instance for FY 2026-27
default_cost_model = IndianCostModel()


def get_cost_model() -> IndianCostModel:
    """Get the default Indian cost model instance."""
    return default_cost_model