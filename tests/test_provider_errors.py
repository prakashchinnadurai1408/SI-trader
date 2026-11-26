"""Provider deadlines and upstream errors without network calls or API keys."""
from contextlib import ExitStack
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from nifty100_weekly.nifty100_adapter import llm_connections as llm


class ProviderErrors(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"SI_TRADER_LLM_TIMEOUT_SECONDS": "180"}))
        connection = self.stack.enter_context(patch.object(llm, "connection"))
        connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {
            "provider": "nvidia", "model": "z-ai/glm-5.3-flash", "secret": b"fixture",
            "endpoint": "https://integrate.api.nvidia.com/v1"}
        self.stack.enter_context(patch.object(llm, "protect", return_value=b"fixture"))
        self.opener = self.stack.enter_context(patch.object(llm, "build_opener")).return_value
        self.opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]}).encode()
        self.payload = {"messages": [{"role": "user", "content": "Reply OK"}], "options": {"num_predict": 12}}

    def test_glm_budget_and_chat_options_and_default_deadline(self):
        self.assertEqual(llm.chat("fixture", self.payload)["message"]["content"], "OK")
        request = self.opener.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["max_tokens"], 4096)
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertTrue(body["chat_template_kwargs"]["clear_thinking"])
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 180)

    def test_custom_deadline_and_invalid_configuration(self):
        with patch.dict(os.environ, {"SI_TRADER_LLM_TIMEOUT_SECONDS": "240"}):
            llm.chat("fixture", self.payload)
            self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 240)
        for value in ("0", "301", "nan"):
            with self.subTest(value=value), patch.dict(os.environ, {"SI_TRADER_LLM_TIMEOUT_SECONDS": value}):
                with self.assertRaises(ValueError):
                    llm.provider_timeout()

    def test_timeouts_are_not_retried_and_have_recovery_guidance(self):
        for error in (TimeoutError(), URLError(TimeoutError()), HTTPError("https://fixture", 504, "Timeout", {}, None)):
            with self.subTest(error=type(error).__name__):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = error
                with self.assertRaises(llm.ProviderTimeout) as raised:
                    llm.chat("fixture", self.payload)
                self.assertIn("LLM Configuration", str(raised.exception))
                self.opener.open.assert_called_once()

    def test_connectivity_and_busy_errors_are_upstream_failures(self):
        for error in (URLError("connection refused"), HTTPError("https://fixture", 429, "Busy", {}, None)):
            self.opener.open.side_effect = error
            with self.assertRaises(llm.ProviderUnavailable) as raised:
                llm.chat("fixture", self.payload)
            self.assertEqual(raised.exception.status, 502)

    def test_reasoning_only_truncation_is_explained(self):
        self.opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({
            "choices": [{"message": {"content": None}, "finish_reason": "length"}]}).encode()
        with self.assertRaisesRegex(ValueError, "output budget"):
            llm.chat("fixture", self.payload)
