"""Admin Dashboard for SI-Trader Platform.

BRD Section 27: Admin operations - CRUD, user management, compliance monitoring.
Extends the existing dashboard with admin-specific features.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import json
import os
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from copy import deepcopy

from .tutorial_system import TutorialStatus, TutorialTopic, get_all_modules, init_user_data_dir, save_user_progress, load_user_progress
from .referral_program import ReferralStatus, RewardTier, UserReferralStats, init_referral_system, get_user_referral_stats
from .pricing_model import SubscriptionTier, SUBSCRIPTION_PLANS, get_plan, init_pricing
from .community_forum import PostStatus, PostType, ForumPost, ForumThread, init_forum, get_forum_stats


ADMIN_DATA_DIR = Path(__file__).parent.parent / "admin_data"
ADMIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = ADMIN_DATA_DIR / "users.json"
GATES_FILE = ADMIN_DATA_DIR / "compliance_gates.json"
LOGS_FILE = ADMIN_DATA_DIR / "admin_logs.json"


# Admin action types
class AdminAction(Enum):
    """Types of admin actions."""
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    GATE_TOGGLE = "gate_toggle"
    SUBSCRIPTION_UPDATE = "subscription_update"
    REFERRAL_PROCESS = "referral_process"
    SYSTEM_BACKUP = "system_backup"


@dataclass
class AdminUser:
    """Admin user account."""
    id: str
    username: str
    role: str  # "admin", "compliance", "manager", "trader"
    email: str = ""
    phone: str = ""
    is_active: bool = True
    last_login: Optional[datetime] = None
    login_attempts: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


@dataclass
class ComplianceGate:
    """A compliance gate status."""
    name: str  # e.g., "backtest", "paper_trading", "compliance", "risk", "capital"
    passed: bool = False
    checked_at: Optional[datetime] = None
    checked_by: str = ""  # admin username
    evidence: Optional[dict] = None


@dataclass
class AdminSession:
    """An admin session log entry."""
    id: str
    admin_id: str
    action: AdminAction
    target: str  # user ID, gate name, etc.
    details: str = ""
    ip_address: str = ""
    success: bool = True
    timestamp: datetime = field(default_factory=datetime.now)


# In-memory storage (backed by disk)
_admin_users: Dict[str, AdminUser] = {}
_compliance_gates: Dict[str, ComplianceGate] = {}
_admin_logs: List[AdminSession] = []
_system_initialized: bool = False


def _ensure_init():
    """Ensure admin data is initialized from disk."""
    global _system_initialized
    
    if _system_initialized:
        return
    
    # Load users
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, 'r') as f:
                users_data = json.load(f)
                for uid, udata in users_data.items():
                    _admin_users[uid] = AdminUser(
                        id=uid,
                        username=udata.get("username", uid),
                        role=udata.get("role", "trader"),
                        email=udata.get("email", ""),
                        phone=udata.get("phone", ""),
                        is_active=udata.get("is_active", True),
                        last_login=datetime.fromisoformat(udata["last_login"]) if udata.get("last_login") else None,
                        login_attempts=udata.get("login_attempts", 0),
                        created_at=datetime.fromisoformat(udata["created_at"]) if udata.get("created_at") else datetime.now(),
                        last_activity=datetime.fromisoformat(udata["last_activity"]) if udata.get("last_activity") else datetime.now(),
                    )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    
    # Load compliance gates
    if GATES_FILE.exists():
        try:
            with open(GATES_FILE, 'r') as f:
                gates_data = json.load(f)
                for gname, gdata in gates_data.items():
                    _compliance_gates[gname] = ComplianceGate(
                        name=gname,
                        passed=gdata.get("passed", False),
                        checked_at=datetime.fromisoformat(gdata["checked_at"]) if gdata.get("checked_at") else None,
                        checked_by=gdata.get("checked_by", ""),
                        evidence=gdata.get("evidence")
                    )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    
    # Load logs
    if LOGS_FILE.exists():
        try:
            with open(LOGS_FILE, 'r') as f:
                logs_data = json.load(f)
                for ld in logs_data:
                    _admin_logs.append(AdminSession(
                        id=ld["id"],
                        admin_id=ld["admin_id"],
                        action=AdminAction(ld["action"]) if ld["action"] in [a.value for a in AdminAction] else AdminAction.SYSTEM_BACKUP,
                        target=ld.get("target", ""),
                        details=ld.get("details", ""),
                        ip_address=ld.get("ip_address", ""),
                        success=ld.get("success", True),
                        timestamp=datetime.fromisoformat(ld["timestamp"]) if ld.get("timestamp") else datetime.now(),
                    ))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    
    _system_initialized = True


def _save_users():
    """Save users to disk."""
    _ensure_init()
    users_data = {}
    for uid, user in _admin_users.items():
        users_data[uid] = {
            "username": user.username,
            "role": user.role,
            "email": user.email,
            "phone": user.phone,
            "is_active": user.is_active,
            "last_login": user.last_login.isoformat() if user.last_login else "",
            "login_attempts": user.login_attempts,
            "created_at": user.created_at.isoformat(),
            "last_activity": user.last_activity.isoformat(),
        }
    with open(USERS_FILE, 'w') as f:
        json.dump(users_data, f, indent=2)


def _save_gates():
    """Save compliance gates to disk."""
    _ensure_init()
    gates_data = {}
    for gname, gate in _compliance_gates.items():
        gates_data[gname] = {
            "passed": gate.passed,
            "checked_at": gate.checked_at.isoformat() if gate.checked_at else "",
            "checked_by": gate.checked_by,
            "evidence": gate.evidence,
        }
    with open(GATES_FILE, 'w') as f:
        json.dump(gates_data, f, indent=2)


def _save_logs():
    """Save admin logs to disk."""
    _ensure_init()
    logs_data = [{"id": log.id, "admin_id": log.admin_id, "action": log.action.value,
                  "target": log.target, "details": log.details,
                  "ip_address": log.ip_address, "success": log.success,
                  "timestamp": log.timestamp.isoformat()} for log in _admin_logs]
    with open(LOGS_FILE, 'w') as f:
        json.dump(logs_data, f, indent=2)


def init_admin():
    """Initialize the admin system."""
    global _system_initialized
    _ensure_init()
    _save_users()
    _save_gates()
    _save_logs()


def create_admin_user(username: str, role: str = "admin", email: str = "", phone: str = "") -> AdminUser:
    """Create a new admin user."""
    _ensure_init()
    
    # Check if username already exists
    for uid, user in _admin_users.items():
        if user.username == username:
            raise ValueError(f"Admin username '{username}' already exists")
    
    user_id = hashlib.sha256(f"admin:{username}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]
    user = AdminUser(
        id=user_id,
        username=username,
        role=role,
        email=email,
        phone=phone,
    )
    
    _admin_users[user_id] = user
    _save_users()
    return user


def get_admin_user(user_id: str) -> Optional[AdminUser]:
    """Get an admin user by ID."""
    _ensure_init()
    return _admin_users.get(user_id)


def get_admin_user_by_username(username: str) -> Optional[AdminUser]:
    """Get an admin user by username."""
    _ensure_init()
    for uid, user in _admin_users.items():
        if user.username == username:
            return user
    return None


def list_admin_users() -> List[AdminUser]:
    """List all admin users."""
    _ensure_init()
    return list(_admin_users.values())


def update_admin_user(user_id: str, **kwargs) -> AdminUser:
    """Update an admin user."""
    _ensure_init()
    
    user = _admin_users.get(user_id)
    if user is None:
        raise ValueError(f"Admin user {user_id} not found")
    
    for key, value in kwargs.items():
        if hasattr(user, key):
            setattr(user, key, value)
    
    user.last_activity = datetime.now()
    _save_users()
    return user


def toggle_compliance_gate(gate_name: str, passed: bool, admin_username: str, evidence: Optional[dict] = None) -> ComplianceGate:
    """Toggle a compliance gate pass/fail status."""
    _ensure_init()
    
    gate = ComplianceGate(
        name=gate_name,
        passed=passed,
        checked_at=datetime.now(),
        checked_by=admin_username,
        evidence=evidence,
    )
    
    _compliance_gates[gate_name] = gate
    _save_gates()
    return gate


def get_compliance_gate(gate_name: str) -> Optional[ComplianceGate]:
    """Get a compliance gate status."""
    _ensure_init()
    return _compliance_gates.get(gate_name)


def list_compliance_gates() -> List[ComplianceGate]:
    """List all compliance gates."""
    _ensure_init()
    return list(_compliance_gates.values())


def check_all_gates() -> Dict[str, bool]:
    """Check the status of all compliance gates."""
    _ensure_init()
    return {name: gate.passed for name, gate in _compliance_gates.items()}


def log_admin_action(admin_id: str, action: AdminAction, target: str, details: str = "",
                     ip_address: str = "", success: bool = True) -> AdminSession:
    """Log an admin action."""
    _ensure_init()
    
    session = AdminSession(
        id=hashlib.sha256(f"{admin_id}:{action.value}:{datetime.now().isoformat()}".encode()).hexdigest()[:12],
        admin_id=admin_id,
        action=action,
        target=target,
        details=details,
        ip_address=ip_address,
        success=success,
    )
    
    _admin_logs.append(session)
    _save_logs()
    return session


def get_admin_logs(limit: int = 100, action: Optional[AdminAction] = None) -> List[AdminSession]:
    """Get admin action logs."""
    _ensure_init()
    
    logs = _admin_logs[-limit:]  # Last N logs
    
    if action is not None:
        logs = [log for log in logs if log.action == action]
    
    return logs


def get_system_stats() -> Dict:
    """Get overall system statistics."""
    _ensure_init()
    
    # User stats
    total_users = len(_admin_users)
    active_users = len([u for u in _admin_users.values() if u.is_active])
    
    # Gate stats
    gate_stats = check_all_gates()
    passed_gates = sum(1 for v in gate_stats.values() if v)
    total_gates = len(gate_stats)
    
    # Referral stats
    from .referral_program import init_referral_system, get_user_referral_stats
    init_referral_system()
    
    # Tutorial stats
    from .tutorial_system import init_user_data_dir, load_user_progress
    init_user_data_dir()
    
    # Pricing stats
    from .pricing_model import init_pricing, SUBSCRIPTION_PLANS
    init_pricing()
    
    # Forum stats
    from .community_forum import init_forum, get_forum_stats
    init_forum()
    forum_stats = get_forum_stats()
    
    return {
        "total_admin_users": total_users,
        "active_admin_users": active_users,
        "compliance_gates": {
            "passed": passed_gates,
            "total": total_gates,
            "pass_rate": round(passed_gates / total_gates * 100, 1) if total_gates > 0 else 0
        },
        "forum_activity": forum_stats,
        "system_initialized": _system_initialized,
    }


def admin_required(func):
    """Decorator to require admin authentication for a function."""
    from functools import wraps
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        # In a real app, this would check session/auth
        # For now, just execute the function
        return func(*args, **kwargs)
    return wrapper


# Export for web app integration
__all__ = [
    'AdminUser', 'ComplianceGate', 'AdminSession', 'AdminAction',
    'init_admin', 'create_admin_user', 'get_admin_user',
    'get_admin_user_by_username', 'list_admin_users', 'update_admin_user',
    'toggle_compliance_gate', 'get_compliance_gate', 'list_compliance_gates',
    'check_all_gates', 'log_admin_action', 'get_admin_logs',
    'get_system_stats', 'admin_required', 'ADMIN_DATA_DIR'
]