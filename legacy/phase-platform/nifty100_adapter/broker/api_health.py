"""Broker API Health & Production Readiness.

BRD Reference: Sections 14 (compliance gates), 27 (admin dashboard).
Provides API key management, static IP validation, connection health monitoring,
and failover procedures for production trading readiness.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import json
import os
import hashlib
from datetime import datetime, timedelta
from pathlib import Path


class APIProvider(Enum):
    """Supported broker API providers."""
    ZERODHA = "zerodha"
    HDFC = "hdfc"
    ANGEL_ONE = "angel_one"
    UPSTOX = "upstox"
    FYERS = "fyers"


class APIStatus(Enum):
    """API connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    HALTED = "halted"  # Market halted


class IPValidationStatus(Enum):
    """Static IP validation status."""
    UNVALIDATED = "unvalidated"
    VALIDATED = "validated"
    BLOCKED = "blocked"
    CHANGED = "changed"


@dataclass
class APICredentials:
    """Securely stored API credentials."""
    provider: APIProvider
    api_key: str  # In production, encrypted at rest
    api_secret: str  # In production, encrypted at rest
    access_token: str  # Refresh automatically
    refresh_token: str
    expiry: Optional[datetime] = None
    last_refreshed: datetime = field(default_factory=datetime.now)
    
    def is_expired(self) -> bool:
        """Check if access token is expired."""
        if self.expiry is None:
            return False
        return datetime.now() > self.expiry
    
    def time_until_expiry(self) -> Optional[timedelta]:
        """Get time until token expiry."""
        if self.expiry is None:
            return None
        return self.expiry - datetime.now()


@dataclass
class IPValidationResult:
    """Result of static IP validation."""
    status: IPValidationStatus
    registered_ip: str
    current_ip: str
    last_checked: datetime
    days_until_rotation: Optional[int] = None  # For IP rotation planning


@dataclass
class APIHealthStatus:
    """Overall API health status."""
    provider: APIProvider
    status: APIStatus
    connected_at: Optional[datetime]
    latency_ms: Optional[float]
    error_count_24h: int = 0
    last_error: Optional[str] = None
    rate_limit_reset: Optional[datetime] = None
    features_available: Dict[str, bool] = field(default_factory=dict)


# Storage paths
CREDENTIALS_DIR = Path(__file__).parent.parent / "user_data" / "api_credentials"
CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"

IP_VALIDATION_DIR = Path(__file__).parent.parent / "user_data" / "ip_validation"
IP_VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
IP_VALIDATION_FILE = IP_VALIDATION_DIR / "validation.json"


# In-memory state
_api_credentials: Dict[str, APICredentials] = {}
_api_health: Dict[str, APIHealthStatus] = {}
_ip_validation: Dict[str, IPValidationResult] = {}


def _load_credentials():
    """Load API credentials from disk."""
    global _api_credentials
    if CREDENTIALS_FILE.exists():
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                data = json.load(f)
                for key, cred_data in data.items():
                    _api_credentials[key] = APICredentials(
                        provider=APIProvider(cred_data["provider"]),
                        api_key=cred_data.get("api_key", ""),
                        api_secret=cred_data.get("api_secret", ""),
                        access_token=cred_data.get("access_token", ""),
                        refresh_token=cred_data.get("refresh_token", ""),
                        expiry=datetime.fromisoformat(cred_data["expiry"]) if cred_data.get("expiry") else None,
                        last_refreshed=datetime.fromisoformat(cred_data["last_refreshed"]) if cred_data.get("last_refreshed") else datetime.now(),
                    )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass


def _save_credentials():
    """Save API credentials to disk."""
    data = {}
    for key, cred in _api_credentials.items():
        data[key] = {
            "provider": cred.provider.value,
            "api_key": cred.api_key,
            "api_secret": cred.api_secret,
            "access_token": cred.access_token,
            "refresh_token": cred.refresh_token,
            "expiry": cred.expiry.isoformat() if cred.expiry else "",
            "last_refreshed": cred.last_refreshed.isoformat(),
        }
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def _load_ip_validation():
    """Load IP validation state from disk."""
    global _ip_validation
    if IP_VALIDATION_FILE.exists():
        try:
            with open(IP_VALIDATION_FILE, 'r') as f:
                data = json.load(f)
                for key, val_data in data.items():
                    _ip_validation[key] = IPValidationResult(
                        status=IPValidationStatus(val_data["status"]),
                        registered_ip=val_data["registered_ip"],
                        current_ip=val_data["current_ip"],
                        last_checked=datetime.fromisoformat(val_data["last_checked"]) if val_data.get("last_checked") else datetime.now(),
                        days_until_rotation=val_data.get("days_until_rotation"),
                    )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass


def _save_ip_validation():
    """Save IP validation state to disk."""
    data = {}
    for key, val in _ip_validation.items():
        data[key] = {
            "status": val.status.value,
            "registered_ip": val.registered_ip,
            "current_ip": val.current_ip,
            "last_checked": val.last_checked.isoformat(),
            "days_until_rotation": val.days_until_rotation,
        }
    with open(IP_VALIDATION_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def _ensure_load():
    """Ensure data structures are loaded from disk."""
    _load_credentials()
    _load_ip_validation()


# Public API functions

def set_credentials(provider: APIProvider, api_key: str, api_secret: str, 
                    access_token: str, refresh_token: str, expiry: Optional[datetime] = None) -> APICredentials:
    """Set/API credentials for a broker."""
    _ensure_load()
    
    key = provider.value
    cred = APICredentials(
        provider=provider,
        api_key=api_key,
        api_secret=api_secret,
        access_token=access_token,
        refresh_token=refresh_token,
        expiry=expiry,
    )
    
    _api_credentials[key] = cred
    _save_credentials()
    return cred


def get_credentials(provider: APIProvider) -> Optional[APICredentials]:
    """Get credentials for a broker provider."""
    _ensure_load()
    return _api_credentials.get(provider.value)


def delete_credentials(provider: APIProvider) -> bool:
    """Delete credentials for a broker provider."""
    _ensure_load()
    key = provider.value
    if key in _api_credentials:
        del _api_credentials[key]
        _save_credentials()
        return True
    return False


def validate_static_ip(provider: APIProvider, registered_ip: str, current_ip: str) -> IPValidationResult:
    """Validate that the current IP matches the registered static IP."""
    _ensure_load()
    
    # Update current IP
    validation_key = provider.value
    ip_result = IPValidationResult(
        status=IPValidationStatus.VALIDATED if registered_ip == current_ip else IPValidationStatus.BLOCKED,
        registered_ip=registered_ip,
        current_ip=current_ip,
        last_checked=datetime.now(),
    )
    
    # If IP changed, mark as needing re-validation
    if registered_ip != current_ip:
        ip_result.status = IPValidationStatus.CHANGED
    
    _ip_validation[validation_key] = ip_result
    _save_ip_validation()
    return ip_result


def get_ip_validation(provider: APIProvider) -> Optional[IPValidationResult]:
    """Get IP validation status for a broker."""
    _ensure_load()
    return _ip_validation.get(provider.value)


def set_api_health(provider: APIProvider, status: APIStatus, latency_ms: Optional[float] = None,
                   error_count: int = 0, last_error: Optional[str] = None,
                   rate_limit_reset: Optional[datetime] = None, features: Optional[Dict[str, bool]] = None) -> APIHealthStatus:
    """Set API health status."""
    _ensure_load()
    
    health = APIHealthStatus(
        provider=provider,
        status=status,
        connected_at=datetime.now() if status in [APIStatus.CONNECTED, APIStatus.RATE_LIMITED] else None,
        latency_ms=latency_ms,
        error_count_24h=error_count,
        last_error=last_error,
        rate_limit_reset=rate_limit_reset,
        features_available=features or {},
    )
    
    _api_health[provider.value] = health
    return health


def get_api_health(provider: APIProvider) -> Optional[APIHealthStatus]:
    """Get API health status for a broker."""
    _ensure_load()
    return _api_health.get(provider.value)


def check_all_health() -> Dict[str, APIHealthStatus]:
    """Get health status for all configured brokers."""
    _ensure_load()
    return dict(_api_health)


def api_ready_for_trading(provider: APIProvider) -> Tuple[bool, str]:
    """
    Check if API is ready for trading.
    Returns (ready, message).
    """
    _ensure_load()
    
    cred = get_credentials(provider)
    health = get_api_health(provider)
    ip_valid = get_ip_validation(provider)
    
    # Check credentials exist and are not obviously broken
    if cred is None:
        return False, "No API credentials configured"
    
    if cred.is_expired():
        return False, "API access token expired; refresh required"
    
    # Check IP validation
    if ip_valid is None:
        return False, "IP not validated; register static IP with broker"
    
    if ip_valid.status == IPValidationStatus.BLOCKED:
        return False, "IP blocked; register correct static IP with broker"
    
    if ip_valid.status == IPValidationStatus.UNVALIDATED:
        return False, "IP not yet validated; complete static IP registration"
    
    # Check API health
    if health is None:
        return False, "API health status not available"
    
    if health.status == APIStatus.DISCONNECTED:
        return False, "API disconnected; reconnect required"
    
    if health.status == APIStatus.FAILED:
        return False, f"API failed: {health.last_error or 'unknown error'}"
    
    if health.status == APIStatus.RATE_LIMITED:
        if health.rate_limit_reset and datetime.now() < health.rate_limit_reset:
            return False, f"Rate limited; reset at {health.rate_limit_reset.strftime('%H:%M:%S')}"
        # Reset if enough time has passed
        return True, "Rate limit reset (or recently reset)"
    
    if health.status == APIStatus.HALTED:
        return False, "Market halted; trading suspended"
    
    # All checks passed
    return True, "API ready for trading"


# Initialize on import
_ensure_load()


# Export for web app integration
__all__ = [
    'APIProvider', 'APIStatus', 'IPValidationStatus', 'APICredentials',
    'IPValidationResult', 'APIHealthStatus', 'set_credentials', 'get_credentials',
    'delete_credentials', 'validate_static_ip', 'get_ip_validation',
    'set_api_health', 'get_api_health', 'check_all_health', 'api_ready_for_trading',
    'CREDENTIALS_FILE', 'IP_VALIDATION_FILE'
]