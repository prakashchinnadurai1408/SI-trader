"""Webhook handler regression tests; no network delivery or broker orders."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from nifty100_weekly.nifty100_adapter.web_app import DashboardHandler
from nifty100_weekly.nifty100_adapter.webhooks import WebhookStore


class WebhookAPI(unittest.TestCase):
    def setUp(self):
        self.store = WebhookStore()
        self.webhook = self.store.register("https://fixture.invalid/hook", "fixture-secret")
        self.handler = object.__new__(DashboardHandler)
        self.handler.server = SimpleNamespace(webhook_store=self.store)
        self.responses = []
        self.handler.send_json = lambda status, result: self.responses.append((status, result))
        self.handler.path = "/api/webhooks/test"

    def test_success_and_delivery_failure_return_results_without_name_error(self):
        for delivered in (True, False):
            with self.subTest(delivered=delivered), patch("nifty100_weekly.nifty100_adapter.web_app.deliver_webhook", return_value=delivered) as sender:
                self.handler._handle_webhooks_subpath({"id": self.webhook.id})
            sender.assert_called_once_with(self.webhook.url, self.webhook.secret, "test.ping", {"test": True})
            self.assertEqual(self.responses[-1][0], 200)
            self.assertEqual(self.responses[-1][1]["delivered"], delivered)
            self.assertNotIn(self.webhook.secret, str(self.responses[-1]))

    def test_invalid_requests_fail_validation_before_delivery(self):
        for payload in ({}, {"id": []}, {"id": "missing"},
                        {"id": self.webhook.id, "event": "bad\r\nheader"},
                        {"id": self.webhook.id, "payload": []}):
            with self.subTest(payload=payload), patch("nifty100_weekly.nifty100_adapter.web_app.deliver_webhook") as sender:
                with self.assertRaises(ValueError):
                    self.handler._handle_webhooks_subpath(payload)
                sender.assert_not_called()

    def test_unregister_is_idempotent_and_missing_id_is_clear(self):
        self.handler.path = "/api/webhooks/unregister"
        for expected in (True, False):
            self.handler._handle_webhooks_subpath({"id": self.webhook.id})
            self.assertEqual(self.responses[-1], (200, {"unregistered": expected}))
        with self.assertRaisesRegex(ValueError, "register or list"):
            self.handler._handle_webhooks_subpath({})
