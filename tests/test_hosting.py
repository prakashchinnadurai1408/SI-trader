import http.client
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from nifty100_weekly.nifty100_adapter.deployment import Runtime, Sessions, password_hash, password_matches
from nifty100_weekly.nifty100_adapter.llm_connections import protect, save_profile, profiles, delete_profile
from nifty100_weekly.nifty100_adapter.web_app import create_server


class HostedAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "FixturePassword123!"
        cls.runtime = Runtime(True, "https://trader.example", "operator@example.com", password_hash(cls.password))

    def setUp(self):
        self.server = create_server(port=0, runtime=self.runtime)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, body=None, cookie="", origin="https://trader.example", host="trader.example", method=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Host": host, "Origin": origin, "Cookie": cookie, "Content-Type": "application/json"}
        client.request(method or ("GET" if body is None else "POST"), path, None if body is None else json.dumps(body), headers)
        response = client.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        client.close()
        return result

    def login(self):
        status, headers, body = self.request("/api/auth/login", {"email": self.runtime.user, "password": self.password})
        self.assertEqual(status, 200)
        self.assertNotIn(self.password.encode(), body)
        self.assertIn("HttpOnly; Secure; SameSite=Strict", headers["Set-Cookie"])
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_api_requires_auth_even_when_ui_is_bypassed(self):
        for path in ("/api/llm-save", "/api/broker", "/api/broker/connect", "/api/evidence-hunt", "/api/quant-scenario", "/api/monthly-comparison", "/api/strategy", "/api/workspace", "/api/research-jobs", "/api/research-jobs/status"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, {})[0], 401)

    def test_workspace_halt_blocks_weekly_api_without_browser_checks(self):
        cookie = self.login()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"SI_TRADER_RESEARCH_STORE": folder}), patch("nifty100_weekly.nifty100_adapter.web_app.installed_models", return_value=["fixture"]):
            self.assertEqual(self.request("/api/workspace", {"action": "halt"}, cookie)[0], 200)
            status, _, body = self.request("/api/strategy", {"model": "fixture", "objective": "Fixture", "maxPositions": 5, "execution": {}}, cookie)
            self.assertEqual(status, 400)
            self.assertIn("halted", json.loads(body)["error"])

    def test_login_readiness_logout_revokes_cookie(self):
        cookie = self.login()
        status, _, body = self.request("/api/auth/session", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["authenticated"])
        payload = {"start": "2019-01", "end": "2023-12", "capital": 1000000, "run": False}
        with patch.dict(os.environ, {"SI_TRADER_STRATEGY_BUNDLE": ""}):
            self.assertEqual(self.request("/api/monthly-comparison", payload, cookie)[0], 200)
        self.assertEqual(self.request("/api/auth/logout", {}, cookie)[0], 200)
        self.assertEqual(self.request("/api/monthly-comparison", payload, cookie)[0], 401)

    def test_bad_origin_and_host_are_rejected(self):
        cookie = self.login()
        self.assertEqual(self.request("/api/models", {}, cookie, origin="https://evil.example")[0], 403)
        self.assertEqual(self.request("/api/models", {}, cookie, host="evil.example")[0], 403)
        self.assertEqual(self.request("/api/models", {}, cookie, origin="")[0], 403)

    def test_login_rate_limit_and_demo_password_rejection(self):
        for _ in range(10):
            self.assertEqual(self.request("/api/auth/login", {"email": "trader@example.com", "password": "WeeklyDemo123!"})[0], 401)
        self.assertEqual(self.request("/api/auth/login", {"email": self.runtime.user, "password": self.password})[0], 429)

    def test_expired_and_forged_sessions_fail(self):
        cookie = self.login()
        with self.server.sessions.lock:
            self.server.sessions.tokens = {key: time.monotonic() - 1 for key in self.server.sessions.tokens}
        self.assertFalse(json.loads(self.request("/api/auth/session", cookie=cookie)[2])["authenticated"])
        self.assertEqual(self.request("/api/models", {}, "__Host-si_trader=forged")[0], 401)

    def test_health_and_static_assets_need_no_model_or_credentials(self):
        for path in ("/healthz", "/", "/app.js", "/app.css"):
            self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(json.loads(self.request("/healthz")[2]), {"status": "ok", "paper": True})

    def test_malformed_login_is_rejected(self):
        self.assertEqual(self.request("/api/auth/login", ["bad"])[0], 400)
        self.assertEqual(self.request("/api/auth/login", {"email": "ü@example.com", "password": None})[0], 401)


class HostingConfiguration(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows DPAPI compatibility")
    def test_existing_windows_keys_remain_readable_when_portable_key_is_added(self):
        with patch.dict(os.environ, {}, clear=True):
            old = protect(b"fixture-old-windows-key")
        with patch.dict(os.environ, {"SI_TRADER_ENCRYPTION_KEY": Fernet.generate_key().decode()}):
            self.assertEqual(protect(old, decrypt=True), b"fixture-old-windows-key")

    def test_ollama_uses_configured_service_without_cloud_calls(self):
        from nifty100_weekly.nifty100_adapter.ai_strategy import ollama
        with patch.dict(os.environ, {"SI_TRADER_OLLAMA_URL": "https://ollama.example:1443"}), patch("http.client.HTTPSConnection") as client:
            client.return_value.getresponse.return_value.status = 200
            client.return_value.getresponse.return_value.read.return_value = b'{"models":[]}'
            self.assertEqual(ollama("/api/tags"), {"models": []})
            client.assert_called_once_with("ollama.example", 1443, timeout=10)

    def test_local_network_boundary(self):
        with patch.dict(os.environ, {"SI_TRADER_MODE": "local"}):
            self.assertFalse(Runtime.environment().hosted)
            with self.assertRaises(ValueError):
                create_server("0.0.0.0", 0)

    def test_hosted_startup_requires_all_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {"SI_TRADER_MODE": "hosted", "SI_TRADER_PUBLIC_ORIGIN": "https://trader.example",
                   "SI_TRADER_AUTH_USER": "operator@example.com", "SI_TRADER_AUTH_PASSWORD_HASH": password_hash("FixturePassword123!"),
                   "SI_TRADER_ENCRYPTION_KEY": Fernet.generate_key().decode(), "SI_TRADER_DATA_DIR": folder}
            with patch.dict(os.environ, env, clear=True):
                self.assertTrue(Runtime.environment().hosted)
                self.assertTrue(os.environ["SI_TRADER_LLM_HOME"].startswith(folder))
            for missing in env:
                if missing == "SI_TRADER_MODE":
                    continue
                broken = {**env, missing: ""}
                with self.subTest(setting=missing), patch.dict(os.environ, broken, clear=True):
                    with self.assertRaises(ValueError):
                        Runtime.environment()

    def test_hash_is_salted_and_wrong_password_fails(self):
        first = password_hash("FixturePassword123!")
        self.assertNotEqual(first, password_hash("FixturePassword123!"))
        self.assertTrue(password_matches("FixturePassword123!", first))
        self.assertFalse(password_matches("OtherPassword123!", first))

    def test_portable_secret_storage_survives_connection_reopen(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SI_TRADER_LLM_HOME": folder, "SI_TRADER_ENCRYPTION_KEY": Fernet.generate_key().decode()
        }):
            identifier = save_profile({"provider": "openai", "label": "Test", "model": "fixture", "apiKey": "fixture-not-a-real-key"})["id"]
            self.assertTrue(profiles()[0]["hasKey"])
            raw = (Path(folder) / "llm.sqlite").read_bytes()
            self.assertNotIn(b"fixture-not-a-real-key", raw)
            secret = protect(b"fixture-secret")
            self.assertEqual(protect(secret, decrypt=True), b"fixture-secret")
            with patch.dict(os.environ, {"SI_TRADER_ENCRYPTION_KEY": Fernet.generate_key().decode()}):
                with self.assertRaises(ValueError):
                    protect(secret, decrypt=True)
            delete_profile(identifier, key_only=True)
            self.assertFalse(profiles()[0]["hasKey"])


if __name__ == "__main__":
    unittest.main()
