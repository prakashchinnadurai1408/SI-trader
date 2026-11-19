"""Pricing Model for SI-Trader Platform.

BRD Section 26: Tiered subscription plans for auto-investing services.
Free tier, Pro tier, and Premium tier with escalating features.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import json
import os
from pathlib import Path


class SubscriptionTier(Enum):
    """Available subscription tiers."""
    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"


class BillingCycle(Enum):
    """Billing cycle options."""
    MONTHLY = "monthly"
    YEARLY = "yearly"  # 2 months free on annual


@dataclass
class PlanFeature:
    """A single feature included in a subscription plan."""
    name: str
    description: str
    included: bool = False  # Whether this feature is included in the tier

    def __str__(self):
        status = "🟢" if self.included else "🔴"
        return f"{status} {self.name}"


# Define the FREE plan first (no references to other tiers)
FREE_PLAN_features: Dict[str, PlanFeature] = {
    "weekly_pipeline": PlanFeature(
        name="Weekly Auto-Investing Pipeline",
        description="Run the BRD Section 27.5 weekly selection pipeline",
        included=True
    ),
    "parameter_catalogue": PlanFeature(
        name="Parameter Catalogue",
        description="Access to 30 enabled parameters with weights",
        included=True
    ),
    "cost_model": PlanFeature(
        name="Indian Cost & Tax Model",
        description="STT 0.1%, STCG 20%, roundtrip ~0.38%",
        included=True
    ),
    "paper_trading": PlanFeature(
        name="Paper Trading Mode",
        description="Default PAPER mode with kill switch",
        included=True
    ),
    "daily_checklist": PlanFeature(
        name="08:30 Pre-Market Checklist",
        description="14-item daily checklist per BRD Section 20",
        included=True
    ),
    "vtm_filter": PlanFeature(
        name="Veto Rules",
        description="Liquidity, ASM/GSM, legal, pledging vetoes",
        included=True
    ),
    "position_limits": PlanFeature(
        name="Position Limits",
        description="Max 10 positions, max 5% per trade",
        included=True
    ),
    "real_time_quotes": PlanFeature(
        name="Real-Time Quotes",
        description="Live NSE quotes via broker API",
        included=False
    ),
    "midcap_universe": PlanFeature(
        name="Midcap Universe",
        description="39 mid-cap stocks beyond Nifty 100",
        included=False
    ),
    "real_money_transition": PlanFeature(
        name="REAL_MONEY Transition",
        description="Requires 3+ months paper trading + SEBI review",
        included=False
    ),
    "tutorial_system": PlanFeature(
        name="Tutorial System",
        description="Interactive onboarding tutorials (BRD Section 23)",
        included=False
    ),
    "community_forum": PlanFeature(
        name="Community Forum",
        description="Discussion board for strategies (BRD Section 24)",
        included=False
    ),
}

FREE_PLAN_LIMITATIONS: Dict[str, str] = {
    "max_positions": "5 positions per weekly basket",
    "data_access": "Nifty 100 only (54 large-cap stocks)",
    "api_access": "No broker API integration",
    "edge_calibration": "Synthetic edge only; no real market edge guaranteed",
}

FREE_PLAN_BENEFITS: List[str] = [
    "Start auto-investing immediately with Rs. 25,000 pilot capital",
    "All BRD compliance gates active",
    "E2E tested pipeline (all 6 phases pass)",
    "Educational tutorials and onboarding",
]

FREE_PLAN = type('FREE_PLAN', (), {
    'tier': SubscriptionTier.FREE,
    'name': 'Free Starter',
    'price_monthly': 0.0,
    'price_yearly': 0.0,
    'features': FREE_PLAN_features,
    'limitations': FREE_PLAN_LIMITATIONS,
    'benefits': FREE_PLAN_BENEFITS,
})


# Define the PRO plan (references FREE plan features)
PRO_PLAN_features: Dict[str, PlanFeature] = {
    # Inherit all FREE features
    **FREE_PLAN_features,
    "real_time_quotes": PlanFeature(
        name="Real-Time Quotes",
        description="Live NSE quotes via broker API (Zerodha/Kite, HDFC, Angel One, Upstox, Fyers)",
        included=True
    ),
    "midcap_universe": PlanFeature(
        name="Midcap Universe",
        description="39 mid-cap stocks beyond Nifty 100 with dynamic liquidity thresholds",
        included=True
    ),
    "tutorial_system": PlanFeature(
        name="Tutorial System",
        description="Full interactive onboarding tutorials (BRD Section 23)",
        included=True
    ),
    "community_forum": PlanFeature(
        name="Community Forum",
        description="Post/read strategy discussions (BRD Section 24)",
        included=True
    ),
    "parameter_toggling": PlanFeature(
        name="Parameter Toggling",
        description="Enable/disable parameters per trading session",
        included=True
    ),
    "advanced_stats": PlanFeature(
        name="Advanced Statistics",
        description="Historical backtest results, edge analysis, win-rate tracking",
        included=True
    ),
}

PRO_PLAN_LIMITATIONS: Dict[str, str] = {
    "max_positions": "10 positions per weekly basket (vs 5 on Free)",
    "data_access": "Nifty 100 + 39 mid-cap stocks (93 total)",
    "api_access": "Broker API integration supported (requires API keys & static IP)",
    "real_money": "Still requires 3+ months paper trading + SEBI review",
}

PRO_PLAN_BENEFITS: List[str] = [
    "Real-time market data via chosen broker",
    "Access to midcap strategy edge (0.15% avg after costs+tax)",
    "Full tutorial system for onboarding new traders",
    "Community forum for strategy sharing and collaboration",
    "Parameter toggling for session-specific configuration",
    "Advanced backtest analytics and edge tracking",
    "Priority support",
]

PRO_PLAN = type('PRO_PLAN', (), {
    'tier': SubscriptionTier.PRO,
    'name': 'Pro Trader',
    'price_monthly': 499.0,
    'price_yearly': 4990.0,  # ~16% discount vs monthly
    'features': PRO_PLAN_features,
    'limitations': PRO_PLAN_LIMITATIONS,
    'benefits': PRO_PLAN_BENEFITS,
})


# Define the PREMIUM plan (references PRO plan features)
PREMIUM_PLAN_features: Dict[str, PlanFeature] = {
    # Inherit all PRO features
    **PRO_PLAN_features,
    "real_money_transition": PlanFeature(
        name="REAL_MONEY Transition Accelerator",
        description="Expedited SEBI review pathway, dedicated support",
        included=True
    ),
    "personalized_parameters": PlanFeature(
        name="Personalized Parameter Weights",
        description="Custom weight optimization based on trader history",
        included=True
    ),
    "priority_signal": PlanFeature(
        name="Priority Trade Execution",
        description="Faster order processing in paper trading mode",
        included=True
    ),
    "dedicated_dashboard": PlanFeature(
        name="Dedicated Admin Dashboard",
        description="Custom dashboard with personal performance metrics",
        included=True
    ),
    "mentor_access": PlanFeature(
        name="Mentor Access",
        description="Monthly live Q&A with strategy developer",
        included=True
    ),
    "multi_broker": PlanFeature(
        name="Multi-Broker Support",
        description="Simultaneous integration with 2+ brokers",
        included=True
    ),
}

PREMIUM_PLAN_LIMITATIONS: Dict[str, str] = {
    "max_positions": "15 positions per weekly basket",
    "data_access": "Nifty 100 + 39 mid-cap + selected small-cap universe",
    "api_access": "Full broker API integration with multiple accounts",
    "usage_limits": "Higher weekly trade volume allowances",
}

PREMIUM_PLAN_BENEFITS: List[str] = [
    "Accelerated REAL_MONEY transition pathway",
    "Personalized parameter optimization",
    "Mentor access and priority support",
    "Multi-broker flexibility",
    "Dedicated performance dashboard",
    "Early access to new features and midcap universe expansions",
]

PREMIUM_PLAN = type('PREMIUM_PLAN', (), {
    'tier': SubscriptionTier.PREMIUM,
    'name': 'Premium Advisor',
    'price_monthly': 1499.0,
    'price_yearly': 14990.0,  # ~17% discount vs monthly
    'features': PREMIUM_PLAN_features,
    'limitations': PREMIUM_PLAN_LIMITATIONS,
    'benefits': PREMIUM_PLAN_BENEFITS,
})


# Build the SUBSCRIPTION_PLANS dict from the class-like objects
SUBSCRIPTION_PLANS: Dict[SubscriptionTier, any] = {
    SubscriptionTier.FREE: FREE_PLAN,
    SubscriptionTier.PRO: PRO_PLAN,
    SubscriptionTier.PREMIUM: PREMIUM_PLAN,
}


def get_plan(tier: SubscriptionTier) -> Optional[any]:
    """Get a subscription plan by tier."""
    return SUBSCRIPTION_PLANS.get(tier)


def get_plan_by_name(name: str) -> Optional[any]:
    """Get a subscription plan by name."""
    for plan in SUBSCRIPTION_PLANS.values():
        if plan.name == name:
            return plan
    return None


def calculate_effective_price(tier: SubscriptionTier, cycle: str, months: int = 1) -> float:
    """Calculate the effective price for a given billing cycle."""
    plan = SUBSCRIPTION_PLANS[tier]
    if cycle == BillingCycle.MONTHLY.value:
        return plan.price_monthly
    elif cycle == BillingCycle.YEARLY.value:
        # Yearly: price for 12 months
        return plan.price_yearly / 12
    return plan.price_monthly


def get_plan_comparison() -> Dict:
    """Get a comparison of all three tiers."""
    comparison = {
        "free": {
            "tier": SUBSCRIPTION_PLANS[SubscriptionTier.FREE].name,
            "monthly_price": 0.0,
            "yearly_price": 0.0,
            "key_features": [
                "Weekly pipeline",
                "Parameter catalogue",
                "Cost model",
                "Paper trading",
                "Daily checklist",
                "Veto rules",
                "Position limits",
            ],
            "limitations": [
                "5 max positions",
                "Nifty 100 only (54 stocks)",
                "No real-time quotes",
                "No midcap universe",
            ],
            "best_for": "Getting started, learning the platform",
        },
        "pro": {
            "tier": SUBSCRIPTION_PLANS[SubscriptionTier.PRO].name,
            "monthly_price": SUBSCRIPTION_PLANS[SubscriptionTier.PRO].price_monthly,
            "yearly_price": SUBSCRIPTION_PLANS[SubscriptionTier.PRO].price_yearly,
            "key_features": [
                "Everything in Free +",
                "Real-time quotes via broker",
                "Midcap universe (93 stocks)",
                "Full tutorial system",
                "Community forum",
                "Parameter toggling",
                "Advanced statistics",
            ],
            "limitations": [
                "10 max positions",
                "No REAL_MONEY transition yet",
                "API requires static IP registration",
            ],
            "best_for": "Active traders wanting midcap edge",
        },
        "premium": {
            "tier": SUBSCRIPTION_PLANS[SubscriptionTier.PREMIUM].name,
            "monthly_price": SUBSCRIPTION_PLANS[SubscriptionTier.PREMIUM].price_monthly,
            "yearly_price": SUBSCRIPTION_PLANS[SubscriptionTier.PREMIUM].price_yearly,
            "key_features": [
                "Everything in Pro +",
                "REAL_MONEY transition accelerator",
                "Personalized parameter weights",
                "Priority trade execution",
                "Dedicated dashboard",
                "Mentor access (monthly Q&A)",
                "Multi-broker support",
            ],
            "limitations": [
                "15 max positions",
                "Higher volume allowances",
                "SEBI review still required",
            ],
            "best_for": "Advisors and serious multi-strategy operators",
        },
    }
    return comparison


def get_subscription_summary() -> str:
    """Get a text summary of all subscription plans."""
    lines = [
        "=" * 60,
        "SI-TRADER SUBSCRIPTION PLANS (BRD Section 26)",
        "=" * 60,
    ]
    
    for tier, plan in SUBSCRIPTION_PLANS.items():
        lines.append("")
        lines.append(f"{plan.tier.value.upper()}: {plan.name}")
        lines.append(f"  Monthly: ₹{plan.price_monthly:.2f} | Yearly: ₹{plan.price_yearly:.2f} ({(1 - plan.price_yearly/(plan.price_monthly*12))*100:.0f}% discount)")
        lines.append("")
        
        included = [f for f, p in plan.features.items() if p.included]
        lines.append(f"  Included: {', '.join(included) if included else 'None'}")
        
        limited = [f.name for f, p in plan.features.items() if not p.included]
        if limited:
            lines.append(f"  Limited: {', '.join(limited)}")
        
        lines.append(f"  Benefits: {'; '.join(plan.benefits) if plan.benefits else 'None'}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


# Initialize and export
def init_pricing():
    """Initialize the pricing model."""
    pass  # Plans are defined at module load


# Export for web app integration
__all__ = [
    'SubscriptionTier', 'BillingCycle', 'PlanFeature', 'SUBSCRIPTION_PLANS',
    'get_plan', 'get_plan_by_name', 'calculate_effective_price',
    'get_plan_comparison', 'get_subscription_summary', 'init_pricing'
]