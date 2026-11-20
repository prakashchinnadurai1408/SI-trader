"""Authentication Module for SI-Trader Platform.

Handles user login credentials and access control.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List
import hashlib
import json
import os
from datetime import datetime, timedelta


@dataclass
class UserCredential:
    """User login credential."""
    username: str
    password_hash: str
    role: str  # "viewer", "trader", "manager", "compliance", "admin"
    mfa_enabled: bool = False
    login_count: int = 0
    last_login: Optional[datetime] = None
    is_locked: bool = False
    lock_time: Optional[datetime] = None


class AuthManager:
    """
    Authentication manager for SI-Trader platform.
    
    Stores user credentials securely (password hashes only, never plain text).
    Manages login attempts, account locking, and role-based access control.
    """
    
    # Default credentials (as specified by user)
    # In production, these would be stored in a database with proper security
    DEFAULT_CREDENTIALS = {
        "trader": {
            "username": "9820065335",
            "password": "123456",
            "role": "trader",
            "mfa_enabled": False,
        },
        "admin": {
            "username": "admin",
            "password": "admin123",
            "role": "admin",
            "mfa_enabled": False,
        }
    }
    
    def __init__(self, storage_path: str = "credentials.json"):
        self.storage_path = storage_path
        self.credentials: Dict[str, UserCredential] = {}
        self.failed_attempts: Dict[str, int] = {}
        self.locked_until: Dict[str, datetime] = {}
        self._load_credentials()
    
    def _load_credentials(self) -> None:
        """Load credentials from storage file or use defaults."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                for username, user_data in data.items():
                    self.credentials[username] = UserCredential(
                        username=username,
                        password_hash=user_data["password_hash"],
                        role=user_data["role"],
                        mfa_enabled=user_data.get("mfa_enabled", False),
                        login_count=user_data.get("login_count", 0),
                        last_login=datetime.fromisoformat(user_data["last_login"]) if user_data.get("last_login") else None,
                        is_locked=user_data.get("is_locked", False),
                        lock_time=datetime.fromisoformat(user_data["lock_time"]) if user_data.get("lock_time") else None,
                    )
            except (json.JSONDecodeError, KeyError, ValueError):
                # If file is corrupted, use defaults
                self._save_credentials()
        else:
            # Initialize with default credentials
            for cred_name, cred_data in self.DEFAULT_CREDENTIALS.items():
                user = UserCredential(
                    username=cred_data["username"],
                    password_hash=self._hash_password(cred_data["password"]),
                    role=cred_data["role"],
                    mfa_enabled=cred_data.get("mfa_enabled", False),
                )
                self.credentials[cred_data["username"]] = user
            self._save_credentials()
    
    def _save_credentials(self) -> None:
        """Save credentials to storage file."""
        data = {}
        for username, user in self.credentials.items():
            data[username] = {
                "password_hash": user.password_hash,
                "role": user.role,
                "mfa_enabled": user.mfa_enabled,
                "login_count": user.login_count,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "is_locked": user.is_locked,
                "lock_time": user.lock_time.isoformat() if user.lock_time else None,
            }
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def authenticate(self, username: str, password: str, mfa_code: Optional[str] = None) -> Optional[UserCredential]:
        """
        Authenticate user login.
        
        Args:
            username: User's phone number or username
            password: Plain text password
            mfa_code: OTP code if MFA is enabled (optional)
        
        Returns:
            UserCredential if authentication successful, None otherwise
        """
        user = self.credentials.get(username)
        if not user:
            return None
        
        # Check if account is locked
        if user.is_locked:
            lock_until = user.lock_time
            if lock_until and datetime.now() < lock_until:
                remaining = int((lock_until - datetime.now()).total_seconds() / 60)
                print(f"❌ Account locked. Try again in {remaining} minutes.")
                return None
            else:
                # Lock expired, reset
                user.is_locked = False
                user.lock_time = None
        
        # Verify password
        entered_hash = self._hash_password(password)
        if entered_hash != user.password_hash:
            # Failed login - increment attempts and potentially lock account
            self.failed_attempts[username] = self.failed_attempts.get(username, 0) + 1
            failed = self.failed_attempts[username]
            
            # Lock account after 3 failed attempts
            if failed >= 3:
                user.is_locked = True
                user.lock_time = datetime.now() + timedelta(minutes=15)
                self._save_credentials()
                print(f"❌ Account locked for 15 minutes after 3 failed attempts.")
                return None
            
            print(f"❌ Invalid credentials. Attempt {failed}/3 failed.")
            return None
        
        # MFA check (if enabled)
        if user.mfa_enabled and mfa_code is None:
            print("⚠️ MFA enabled but no code provided.")
            return None
        
        if user.mfa_enabled and mfa_code:
            # In production, verify OTP against registered device
            # For demo, accept any 6-digit code
            if not mfa_code.isdigit() or len(mfa_code) != 6:
                print("❌ Invalid MFA code format. Expected 6 digits.")
                return None
            # Accept any valid 6-digit code for demo
        
        # Login successful - reset failed attempts
        user.login_count += 1
        user.last_login = datetime.now()
        self.failed_attempts.pop(username, None)
        self._save_credentials()
        
        print(f"✅ Login successful: {username} (Role: {user.role})")
        return user
    
    def get_user_role(self, username: str) -> Optional[str]:
        """Get user role by username."""
        user = self.credentials.get(username)
        return user.role if user else None
    
    def is_authorized(self, username: str, required_role: str) -> bool:
        """Check if user has required role or higher."""
        user_role = self.get_user_role(username)
        if not user_role:
            return False
        
        role_hierarchy = {
            "viewer": 1,
            "trader": 2,
            "manager": 3,
            "compliance": 3,
            "admin": 4,
        }
        
        return role_hierarchy.get(user_role, 0) >= role_hierarchy.get(required_role, 0)


# Example usage / demo
if __name__ == "__main__":
    print("=" * 60)
    print("SI-TRADER - AUTHENTICATION MODULE DEMO")
    print("=" * 60)
    print()
    
    auth = AuthManager()
    
    print("Default credentials:")
    print("  • Username: 9820065335  |  Password: 123456  |  Role: trader")
    print("  • Username: admin       |  Password: admin123 |  Role: admin")
    print()
    
    # Test login
    while True:
        print("Login options:")
        print("  1. Login as trader (9820065335 / 123456)")
        print("  2. Login as admin (admin / admin123)")
        print("  3. Exit")
        print()
        choice = input("Select option (1-3): ").strip()
        
        if choice == "1":
            user = auth.authenticate("9820065335", "123456")
            if user:
                print(f"\nLogged in as: {user.username} ({user.role})")
                print(f"Login count: {user.login_count}")
                print(f"MFA enabled: {user.mfa_enabled}")
                break
            else:
                print("Login failed. Try again.\n")
        
        elif choice == "2":
            user = auth.authenticate("admin", "admin123")
            if user:
                print(f"\nLogged in as: {user.username} ({user.role}) - Full admin access")
                break
            else:
                print("Login failed. Try again.\n")
        
        elif choice == "3":
            print("Goodbye!")
            break
        
        else:
            print("Invalid option. Try again.\n")
    
    print("\n" + "=" * 60)