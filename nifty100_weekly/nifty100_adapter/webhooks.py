"""Outbound webhook delivery for SI-Trader.

Registers webhook endpoints and delivers signed JSON payloads on platform
events (order placed, trade executed, quote updated, scan breakout).

Delivery is signed with HMAC-SHA256 using the webhook's secret so the
receiver can verify authenticity. Delivery happens on a background thread
so the HTTP handler is never blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional
import hashlib
import hmac
import json
import logging
import threading
import uuid

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
except Exception:  # pragma: no cover
    urlopen = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class Webhook:
    """A registered webhook destination."""
    id: str
    url: str
    secret: str
    events: List[str]          # e.g. ["order.*", "trade.*", "quote.*", "scan.*"]
    active: bool = True
    created_at: Optional[str] = None

    def matches(self, event: str) -> bool:
        for pat in self.events:
            if pat == "*":
                return True
            if pat.endswith(".*"):
                prefix = pat[:-2]
                return event == prefix or event.startswith(prefix + ".")
            if pat == event:
                return True
        return False

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "url": self.url,
            "secret": "***" if self.secret else "",
            "events": self.events,
            "active": self.active,
            "created_at": self.created_at,
        }


def _sign(secret: str, payload: bytes) -> str:
    """HMAC-SHA256 signature hex digest."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def deliver_webhook(
    url: str,
    secret: str,
    event: str,
    payload: Dict[str, object],
    timeout: float = 5.0,
) -> bool:
    """Deliver a signed JSON webhook. Returns True if HTTP 2xx."""
    if urlopen is None:
        logger.error("urllib unavailable - cannot deliver webhook")
        return False
    body = json.dumps(payload, default=str, allow_nan=False).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Signature": f"sha256={_sign(secret, body)}",
        "X-Event": event,
        "X-Delivery-Id": str(uuid.uuid4()),
    }
    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except HTTPError as exc:
        logger.warning("webhook %s HTTP %s", url, exc.code)
        return False
    except URLError as exc:
        logger.warning("webhook %s URL error: %s", url, exc)
        return False
    except Exception as exc:  # pragma: no cover - network
        logger.warning("webhook %s delivery failed: %s", url, exc)
        return False


class WebhookStore:
    """Thread-safe registry of webhook destinations."""

    def __init__(self):
        self._webhooks: Dict[str, Webhook] = {}
        self._lock = threading.Lock()

    def register(
        self,
        url: str,
        secret: str = "",
        events: Optional[List[str]] = None,
        webhook_id: Optional[str] = None,
    ) -> Webhook:
        wid = webhook_id or str(uuid.uuid4())
        wh = Webhook(
            id=wid,
            url=url,
            secret=secret,
            events=events or ["*"],
            active=True,
            created_at=datetime.now().isoformat(),
        )
        with self._lock:
            self._webhooks[wid] = wh
        return wh

    def unregister(self, webhook_id: str) -> bool:
        with self._lock:
            return self._webhooks.pop(webhook_id, None) is not None

    def get(self, webhook_id: str) -> Optional[Webhook]:
        with self._lock:
            return self._webhooks.get(webhook_id)

    def list_all(self) -> List[Webhook]:
        with self._lock:
            return list(self._webhooks.values())

    def active_for(self, event: str) -> List[Webhook]:
        with self._lock:
            return [w for w in self._webhooks.values() if w.active and w.matches(event)]

    def clear(self) -> None:
        with self._lock:
            self._webhooks.clear()


def fire_webhooks(
    store: WebhookStore,
    event: str,
    payload: Dict[str, object],
) -> int:
    """Fire `event` to all matching active webhooks (background threads).

    Returns the number of webhooks dispatched.
    """
    targets = store.active_for(event)
    dispatched = 0
    for wh in targets:
        def _deliver(url=wh.url, secret=wh.secret, ev=event, p=payload):
            try:
                deliver_webhook(url, secret, ev, p)
            except Exception:  # pragma: no cover - background
                logger.exception("webhook delivery thread crashed")
        threading.Thread(target=_deliver, daemon=True).start()
        dispatched += 1
    return dispatched


__all__ = [
    "Webhook", "WebhookStore",
    "deliver_webhook", "fire_webhooks",
]
