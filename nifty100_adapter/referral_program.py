"""Referral Program for SI-Trader Platform.

BRD Section 25: Referral-based user acquisition with rewards.
Tracks referrals, rewards, and conversion milestones.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path


class ReferralStatus(Enum):
    """Status of a referral."""
    PENDING = "pending"      # User signed up, not yet active
    ACTIVE = "active"        # User is active on platform
    CONVERTED = "converted"  # User made first trade/paper trade
    REWARDED = "rewarded"    # Referral reward has been issued


class RewardTier(Enum):
    """Reward tiers for referrals."""
    TIER_1 = "tier_1"   # First referral: 1 week paper trading credit
    TIER_2 = "tier_2"   # Second referral: 2 weeks paper trading credit
    TIER_3 = "tier_3"   # Third referral: 1 month capital allocation preview
    TIER_4 = "tier_4"   # Five referrals: access to REAL_MONEY consideration


@dataclass
class Referral:
    """A referral record."""
    id: str
    referrer_id: str
    referee_id: str
    referee_name: str
    referee_phone: str
    status: ReferralStatus
    created_at: datetime
    converted_at: Optional[datetime]
    rewarded_at: Optional[datetime]
    reward_tier: Optional[RewardTier]
    weeks_paper_trading: int = 0  # Weeks of paper trading credit


@dataclass
class ReferralProgramConfig:
    """Configuration for the referral program."""
    referral_code_length: int = 8
    reward_weeks_per_tier: Dict[RewardTier, int] = field(default_factory=lambda: {
        RewardTier.TIER_1: 1,
        RewardTier.TIER_2: 2,
        RewardTier.TIER_3: 4,
        RewardTier.TIER_4: 0  # Non-weekly reward: REAL_MONEY consideration
    })
    active_referral_limit: int = 50  # Max active referrals per user


@dataclass
class UserReferralStats:
    """Statistics for a user's referral activity."""
    user_id: str
    referrer_id: str
    total_referrals: int = 0
    active_referrals: int = 0
    converted_referrals: int = 0
    rewarded_referrals: int = 0
    total_referral_weeks: int = 0
    next_tier: RewardTier = RewardTier.TIER_1
    referral_code: str = ""


# Referral data storage
REFERRAL_DATA_DIR = Path(__file__).parent.parent / "user_data"
REFERRAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
REFERRAL_INDEX_FILE = REFERRAL_DATA_DIR / "referral_index.json"


def _load_referral_index() -> Dict:
    """Load the referral index from disk."""
    if REFERRAL_INDEX_FILE.exists():
        try:
            with open(REFERRAL_INDEX_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"referrals": [], "users": {}}
    return {"referrals": [], "users": {}}


def _save_referral_index(index: Dict):
    """Save the referral index to disk."""
    with open(REFERRAL_INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=2)


def generate_referral_code() -> str:
    """Generate a unique referral code for a user."""
    timestamp_prefix = datetime.now().strftime("%y%m%d%H%M%S")
    random_suffix = hashlib.sha256(
        f"{datetime.now().microsecond}".encode()
    ).hexdigest()[:4]
    return f"SI{timestamp_prefix}{random_suffix}"[:8]


def create_referrer(user_id: str, user_name: str, user_phone: str) -> Tuple[str, ReferralProgramConfig]:
    """Create a new referrer profile and return (referral_code, config)."""
    referral_code = generate_referral_code()
    
    # Ensure unique code
    index = _load_referral_index()
    while any(r["referral_code"] == referral_code for r in index["referrals"]):
        referral_code = generate_referral_code()
    
    referral = Referral(
        id=hashlib.sha256(f"{user_id}:{referral_code}".encode()).hexdigest()[:12],
        referrer_id=user_id,
        referee_id="",  # Will be filled when someone uses the code
        referee_name="",
        referee_phone=user_phone,
        status=ReferralStatus.PENDING,
        created_at=datetime.now(),
        converted_at=None,
        rewarded_at=None,
        reward_tier=RewardTier.TIER_1
    )
    
    # Update index
    index["referrals"].append({
        "id": referral.id,
        "referrer_id": referral.referrer_id,
        "referee_id": referral.referee_id,
        "referee_name": referral.referee_name,
        "referee_phone": referral.referee_phone,
        "status": referral.status.value,
        "created_at": referral.created_at.isoformat(),
        "reward_tier": referral.reward_tier.value,
        "rewarded_at": referral.rewarded_at.isoformat() if referral.rewarded_at else None,
        "reward_weeks": referral.weeks_paper_trading
    })
    
    # Update user stats
    index["users"][user_id] = {
        "user_id": user_id,
        "referral_code": referral_code,
        "total_referrals": 0,
        "active_referrals": 0,
        "converted_referrals": 0,
        "rewarded_referrals": 0,
        "total_referral_weeks": 0,
        "next_tier": RewardTier.TIER_1.value
    }
    
    _save_referral_index(index)
    
    return referral_code, ReferralProgramConfig()


def register_referral_usage(
    referrer_id: str,
    referee_id: str,
    referee_name: str,
    referee_phone: str
) -> Referral:
    """Register when a referred user signs up/activates."""
    index = _load_referral_index()
    
    # Find the referring referral
    referring_ref = None
    for r in index["referrals"]:
        if r["referrer_id"] == referrer_id and r["status"] == ReferralStatus.PENDING.value:
            referring_ref = r
            break
    
    if referring_ref is None:
        # Create new referral entry
        referring_ref = {
            "id": hashlib.sha256(f"{referrer_id}:referee".encode()).hexdigest()[:12],
            "referrer_id": referrer_id,
            "referee_id": referee_id,
            "referee_name": referee_name,
            "referee_phone": referee_phone,
            "status": ReferralStatus.PENDING.value,
            "created_at": datetime.now().isoformat(),
            "reward_tier": RewardTier.TIER_1.value,
            "rewarded_at": None,
            "reward_weeks": 0
        }
        index["referrals"].append(referring_ref)
    
    # Update status to ACTIVE
    referring_ref["status"] = ReferralStatus.ACTIVE.value
    referring_ref["referee_id"] = referee_id
    referring_ref["referee_name"] = referee_name
    referring_ref["referee_phone"] = referee_phone
    referring_ref["updated_at"] = datetime.now().isoformat()
    
    # Update user stats
    if referrer_id in index["users"]:
        index["users"][referrer_id]["total_referrals"] = index["users"][referrer_id].get("total_referrals", 0) + 1
        index["users"][referrer_id]["active_referrals"] = index["users"][referrer_id].get("active_referrals", 0) + 1
    
    _save_referral_index(index)
    return referring_ref


def convert_referral(
    referrer_id: str,
    referee_id: str
) -> Optional[Referral]:
    """Mark a referral as converted (user made first trade)."""
    index = _load_referral_index()
    
    # Find the referring referral
    referring_ref = None
    for r in index["referrals"]:
        if r["referrer_id"] == referrer_id and r["status"] in [ReferralStatus.PENDING.value, ReferralStatus.ACTIVE.value]:
            referring_ref = r
            break
    
    if referring_ref is None:
        return None
    
    # Update status to CONVERTED
    referring_ref["status"] = ReferralStatus.CONVERTED.value
    referring_ref["converted_at"] = datetime.now().isoformat()
    
    # Update user stats
    if referrer_id in index["users"]:
        index["users"][referrer_id]["converted_referrals"] = index["users"][referrer_id].get("converted_referrals", 0) + 1
        index["users"][referrer_id]["total_referrals"] = index["users"][referrer_id].get("total_referrals", 0) + 1
        index["users"][referrer_id]["active_referrals"] = max(
            index["users"][referrer_id].get("active_referrals", 0) - 1, 0
        )
        
        # Check if reward tier advances
        total_converted = index["users"][referrer_id].get("converted_referrals", 0)
        config = ReferralProgramConfig()
        
        if total_converted >= 2 and index["users"][referrer_id]["next_tier"] == RewardTier.TIER_1:
            index["users"][referrer_id]["next_tier"] = RewardTier.TIER_2
            referring_ref["reward_tier"] = RewardTier.TIER_2.value
            referring_ref["reward_weeks"] = config.reward_weeks_per_tier[RewardTier.TIER_2]
        elif total_converted >= 3 and index["users"][referrer_id]["next_tier"] == RewardTier.TIER_2:
            index["users"][referrer_id]["next_tier"] = RewardTier.TIER_3
            referring_ref["reward_tier"] = RewardTier.TIER_3.value
            referring_ref["reward_weeks"] = config.reward_weeks_per_tier[RewardTier.TIER_3]
        elif total_converted >= 5 and index["users"][referrer_id]["next_tier"] == RewardTier.TIER_3:
            index["users"][referrer_id]["next_tier"] = RewardTier.TIER_4
            referring_ref["reward_tier"] = RewardTier.TIER_4.value
            referring_ref["reward_weeks"] = config.reward_weeks_per_tier[RewardTier.TIER_4]
    
    _save_referral_index(index)
    return referring_ref


def reward_referral(
    referrer_id: str
) -> Optional[Dict]:
    """Issue reward for a referral and return reward details."""
    index = _load_referral_index()
    
    # Find the referring user's stats
    if referrer_id not in index["users"]:
        return None
    
    user_stats = index["users"][referrer_id]
    total_rewarded = user_stats.get("rewarded_referrals", 0)
    next_tier = RewardTier(user_stats["next_tier"])
    
    # Check if reward can be issued
    if next_tier == RewardTier.TIER_4:
        # Tier 4 is REAL_MONEY consideration, not weekly credit
        return {
            "reward_tier": "tier_4_real_money_consideration",
            "message": "5 referrals: REAL_MONEY transition consideration submitted for SEBI review",
            "issued": True
        }
    
    # Issue weekly paper trading credit
    reward_weeks = next_tier.value if hasattr(next_tier, 'value') else 1
    
    # Update stats
    user_stats["rewarded_referrals"] = total_rewarded + 1
    user_stats["total_referral_weeks"] = user_stats.get("total_referral_weeks", 0) + reward_weeks
    
    # Advance to next tier
    if next_tier == RewardTier.TIER_1:
        user_stats["next_tier"] = RewardTier.TIER_2.value
    elif next_tier == RewardTier.TIER_2:
        user_stats["next_tier"] = RewardTier.TIER_3.value
    elif next_tier == RewardTier.TIER_3:
        user_stats["next_tier"] = RewardTier.TIER_4.value
    
    # Mark referral as rewarded
    for r in index["referrals"]:
        if r["referrer_id"] == referrer_id and r["status"] in [ReferralStatus.PENDING.value, ReferralStatus.ACTIVE.value]:
            r["status"] = ReferralStatus.REWARDED.value
            r["rewarded_at"] = datetime.now().isoformat()
            r["reward_tier"] = next_tier.value
            r["reward_weeks"] = reward_weeks
            break
    
    _save_referral_index(index)
    
    return {
        "reward_tier": next_tier.name,
        "reward_weeks": reward_weeks,
        "message": f"{reward_weeks} week(s) paper trading credit issued",
        "issued": True
    }


def get_user_referral_stats(user_id: str) -> UserReferralStats:
    """Get referral statistics for a user."""
    index = _load_referral_index()
    
    if user_id not in index["users"]:
        # Create default stats
        index["users"][user_id] = {
            "user_id": user_id,
            "referral_code": generate_referral_code(),
            "total_referrals": 0,
            "active_referrals": 0,
            "converted_referrals": 0,
            "rewarded_referrals": 0,
            "total_referral_weeks": 0,
            "next_tier": RewardTier.TIER_1.value
        }
        _save_referral_index(index)
    
    user_stats = index["users"][user_id]
    
    # Find all referrals for this user
    total_referrals = 0
    active_referrals = 0
    converted_referrals = 0
    rewarded_referrals = 0
    
    for r in index["referrals"]:
        if r["referrer_id"] == user_id:
            total_referrals += 1
            if r["status"] in [ReferralStatus.ACTIVE.value, ReferralStatus.CONVERTED.value]:
                active_referrals += 1
            if r["status"] == ReferralStatus.CONVERTED.value:
                converted_referrals += 1
            if r["status"] == ReferralStatus.REWARDED.value:
                rewarded_referrals += 1
    
    # Determine next tier
    next_tier = RewardTier(user_stats.get("next_tier", RewardTier.TIER_1.value))
    
    return UserReferralStats(
        user_id=user_id,
        referrer_id=user_id,
        total_referrals=total_referrals,
        active_referrals=active_referrals,
        converted_referrals=converted_referrals,
        rewarded_referrals=rewarded_referrals,
        total_referral_weeks=user_stats.get("total_referral_weeks", 0),
        next_tier=next_tier,
        referral_code=user_stats.get("referral_code", generate_referral_code())
    )


def init_referral_system():
    """Initialize the referral system data structure."""
    _load_referral_index()


# Export for web app integration
__all__ = [
    'ReferralStatus', 'RewardTier', 'Referral', 'ReferralProgramConfig',
    'UserReferralStats', 'generate_referral_code', 'create_referrer',
    'register_referral_usage', 'convert_referral', 'reward_referral',
    'get_user_referral_stats', 'init_referral_system'
]