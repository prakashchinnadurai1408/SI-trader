"""Runtime configuration and single-operator authentication for hosted deployments."""

from collections import deque
from dataclasses import dataclass
import base64
import hashlib
from http.cookies import SimpleCookie, CookieError
import os
from pathlib import Path
import secrets
from threading import Lock
import time
from urllib.parse import urlsplit

COOKIE = "__Host-si_trader"


def password_hash(password):
    if len(password) < 12 or len(password) > 256:
        raise ValueError("Use a password of 12 to 256 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return "scrypt$" + base64.urlsafe_b64encode(salt + digest).decode()


def password_matches(password, encoded):
    try:
        algorithm, value = encoded.split("$", 1)
        raw = base64.b64decode(value, altchars=b"-_", validate=True)
        if algorithm != "scrypt" or len(raw) != 80 or not isinstance(password, str) or not 12 <= len(password) <= 256:
            return False
        digest = hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1)
        return secrets.compare_digest(digest, raw[16:])
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class Runtime:
    hosted: bool = False
    origin: str = ""
    user: str = ""
    password: str = ""

    @classmethod
    def environment(cls):
        mode = os.environ.get("SI_TRADER_MODE", "local")
        if mode not in ("local", "hosted"):
            raise ValueError("SI_TRADER_MODE must be local or hosted.")
        if mode == "local":
            return cls()
        origin = os.environ.get("SI_TRADER_PUBLIC_ORIGIN", "")
        url = urlsplit(origin)
        if (url.scheme != "https" or not url.hostname or url.username or url.password or
                url.path or url.query or url.fragment or any(c.isspace() for c in origin)):
            raise ValueError("Set SI_TRADER_PUBLIC_ORIGIN to an HTTPS origin without a path.")
        user = os.environ.get("SI_TRADER_AUTH_USER", "")
        encoded = os.environ.get("SI_TRADER_AUTH_PASSWORD_HASH", "")
        if not user or len(user) > 254 or "@" not in user:
            raise ValueError("Set SI_TRADER_AUTH_USER to the operator email.")
        try:
            algorithm, value = encoded.split("$", 1)
            if algorithm != "scrypt" or len(base64.b64decode(value, altchars=b"-_", validate=True)) != 80:
                raise ValueError()
        except ValueError:
            raise ValueError("Generate SI_TRADER_AUTH_PASSWORD_HASH with scripts/hosting_secrets.py.") from None
        from cryptography.fernet import Fernet
        try:
            Fernet(os.environ.get("SI_TRADER_ENCRYPTION_KEY", "").encode())
        except ValueError:
            raise ValueError("Set a valid SI_TRADER_ENCRYPTION_KEY before hosting.") from None
        folder = os.environ.get("SI_TRADER_DATA_DIR", "")
        if not folder or not Path(folder).is_absolute():
            raise ValueError("SI_TRADER_DATA_DIR must be an absolute persistent volume path.")
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("SI_TRADER_LLM_HOME", str(root / "models"))
        os.environ.setdefault("SI_TRADER_RESEARCH_STORE", str(root / "research"))
        return cls(True, origin, user, encoded)

    def allowed_host(self, host, port):
        return host == (urlsplit(self.origin).netloc if self.hosted else f"127.0.0.1:{port}")

    def allowed_origin(self, origin, port):
        return origin == (self.origin if self.hosted else f"http://127.0.0.1:{port}")


class Sessions:
    """Opaque, revocable sessions; restarts sign users out. No secrets in cookies."""

    def __init__(self):
        self.lock = Lock()
        self.tokens = {}
        self.attempts = deque(maxlen=10)

    def login(self, user, password, runtime):
        with self.lock:
            now = time.monotonic()
            while self.attempts and self.attempts[0] < now - 900:
                self.attempts.popleft()
            if len(self.attempts) >= 10:
                return None, 429
            self.attempts.append(now)
            if not (isinstance(user, str) and secrets.compare_digest(user.encode(), runtime.user.encode()) and
                    password_matches(password, runtime.password)):
                return None, 401
            self.attempts.clear()
            self.tokens = {k: v for k, v in self.tokens.items() if v > now}
            if len(self.tokens) >= 128:
                self.tokens.pop(next(iter(self.tokens)))
            token = secrets.token_urlsafe(32)
            self.tokens[hashlib.sha256(token.encode()).digest()] = now + 3600
            return token, 200

    def authorized(self, cookie):
        token = self.token(cookie)
        if not token:
            return False
        with self.lock:
            return self.tokens.get(hashlib.sha256(token.encode()).digest(), 0) > time.monotonic()

    @staticmethod
    def token(value):
        try:
            cookie = SimpleCookie()
            cookie.load(value or "")
            return cookie[COOKIE].value if COOKIE in cookie else ""
        except CookieError:
            return ""

    def logout(self, cookie):
        with self.lock:
            self.tokens.pop(hashlib.sha256(self.token(cookie).encode()).digest(), None)

    @staticmethod
    def cookie(token, clear=False):
        return f"{COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={0 if clear else 3600}"
