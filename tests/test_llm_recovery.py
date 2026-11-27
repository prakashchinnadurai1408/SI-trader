"""Exercise slow model jobs and per-role committee settings without paid inference."""
import http.client
import json
import os
import tempfile
from contextlib import ExitStack
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch

from nifty100_weekly.nifty100_adapter import llm_connections as llm
from nifty100_weekly.nifty100_adapter import ai_strategy
from nifty100_weekly.nifty100_adapter.deployment import Runtime
from nifty100_weekly.nifty100_adapter.web_app import create_server


class FallbackTests(unittest.TestCase):
    def test_cloud_prefix_is_stripped_and_local_fallback_uses_ollama(self):
        identifier = "a"*32
        with patch.object(llm,"chat",side_effect=llm.ProviderTimeout("Fixture timeout")) as cloud, patch.object(ai_strategy,"ollama",return_value={"message":{"content":"OK"}}) as local:
            self.assertEqual(llm.chat_with_fallback(["profile:"+identifier,"gemma4:latest"],{"messages":[]})["message"]["content"],"OK")
        cloud.assert_called_once_with(identifier,{"messages":[]})
        self.assertEqual(local.call_args.args[1]["model"],"gemma4:latest")

    def test_all_upstream_timeouts_remain_timeouts(self):
        with patch.object(llm,"chat",side_effect=llm.ProviderTimeout("Fixture timeout")):
            with self.assertRaises(llm.ProviderTimeout):
                llm.chat_with_fallback(["profile:"+"a"*32],{})


class RecoveryAPI(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        folder=self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.dict(os.environ,{"SI_TRADER_LLM_HOME":folder}))
        self.stack.enter_context(patch("nifty100_weekly.nifty100_adapter.web_app.installed_models",return_value=["fixture","profile:"+"a"*32]))
        self.server=create_server(port=0,runtime=Runtime())
        self.thread=Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,payload):
        client=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        client.request("POST",path,json.dumps(payload),{"Origin":f"http://127.0.0.1:{self.server.server_port}","Content-Type":"application/json"})
        response=client.getresponse()
        result=response.status,json.loads(response.read())
        client.close()
        return result

    def test_models_only_committee_request_and_legacy_model_are_accepted(self):
        settings={"maker":["profile:"+"a"*32,"fixture"],"checker":"fixture","umpire":"fixture"}
        with patch("nifty100_weekly.nifty100_adapter.web_app.build_committee",return_value={"status":"fixture"}) as build:
            self.assertEqual(self.request("/api/research-committee",{"models":settings,"objective":"Fixture"})[0],200)
            self.assertEqual(build.call_args.args[0],settings)
            self.assertEqual(self.request("/api/research-committee",{"model":"fixture","objective":"Fixture"})[0],200)
            self.assertEqual(self.request("/api/research-committee",{"models":{"default":"missing"},"objective":"Fixture"})[0],400)
            self.assertEqual(build.call_count,2)

    def test_timeout_is_504_and_a_followup_test_can_succeed(self):
        with patch("nifty100_weekly.nifty100_adapter.web_app.test_model",side_effect=llm.ProviderTimeout("Fixture timeout")):
            status,result=self.request("/api/model-test",{"model":"fixture"})
        self.assertEqual(status,504)
        self.assertEqual(result["code"],"provider_timeout")
        with patch("nifty100_weekly.nifty100_adapter.web_app.test_model",return_value={"model":"fixture","elapsedMs":1}):
            self.assertEqual(self.request("/api/model-test",{"model":"fixture"})[0],200)

    def test_slow_test_runs_in_background_and_duplicate_does_not_repeat(self):
        entered,release=Event(),Event()
        def slow(model):
            entered.set();release.wait(3)
            return {"model":model,"elapsedMs":1}
        payload={"route":"/api/model-test","body":{"model":"fixture"},"requestId":"a"*32}
        with patch("nifty100_weekly.nifty100_adapter.web_app.test_model",side_effect=slow) as test:
            try:
                status,job=self.request("/api/research-jobs",payload)
                self.assertEqual(status,202)
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.request("/api/research-jobs",payload)[1]["id"],job["id"])
            finally:release.set()
            for _ in range(100):
                result=self.request("/api/research-jobs/status",{"id":job["id"]})[1]
                if result["state"]=="succeeded":break
                time.sleep(.01)
            self.assertEqual(result["state"],"succeeded")
            self.assertEqual(test.call_count,1)
