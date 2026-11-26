"""Concurrency, replay protection, ownership and progress for background jobs."""
from threading import Event
import time
import unittest
from unittest.mock import patch
from nifty100_weekly.nifty100_adapter.research_jobs import ResearchJobs, JobBusy, progress


def finished(jobs, owner, identifier):
    for _ in range(300):
        result = jobs.status(owner, identifier)
        if result["state"] in ("succeeded", "failed"):
            return result
        time.sleep(.01)
    raise AssertionError("Fixture job did not finish")


class ResearchJobTests(unittest.TestCase):
    def test_parallel_capacity_progress_idempotency_and_isolation(self):
        jobs = ResearchJobs(capacity=2)
        release = Event()
        entered = [Event(), Event()]
        def run(index):
            progress("Checking catalogue", parametersEvaluated=48, parametersCovered=2, parametersTotal=48)
            entered[index].set()
            release.wait(3)
            return 200, {"fixture": index}
        try:
            one = jobs.start("owner", "/api/strategy", {}, "a"*32, lambda: run(0))
            two = jobs.start("owner", "/api/strategy-builder", {}, "b"*32, lambda: run(1))
            self.assertTrue(all(event.wait(1) for event in entered))
            replay = jobs.start("owner", "/api/strategy", {}, "a"*32, lambda: self.fail("Duplicate inference"))
            self.assertEqual(replay["id"], one["id"])
            resubmitted = jobs.start("owner", "/api/strategy", {}, "d"*32, lambda: self.fail("Duplicate inference"))
            self.assertEqual(resubmitted["id"], one["id"])
            with self.assertRaises(ValueError):
                jobs.start("owner", "/api/strategy", {"different": True}, "a"*32, lambda: None)
            with self.assertRaises(JobBusy):
                jobs.start("owner", "/api/strategy", {"new": True}, "c"*32, lambda: None)
            with self.assertRaises(ValueError):
                jobs.status("another-session", one["id"])
            view = jobs.status("owner", one["id"])
            self.assertEqual(view["details"]["parametersEvaluated"], 48)
            self.assertEqual(view["details"]["parametersCovered"], 2)
            self.assertNotIn("owner", view)
        finally:
            release.set()
        self.assertEqual(finished(jobs, "owner", one["id"])["state"], "succeeded")
        self.assertEqual(finished(jobs, "owner", two["id"])["result"]["fixture"], 1)

    def test_failures_and_eviction_are_bounded(self):
        jobs = ResearchJobs(retained=1)
        one = jobs.start("owner", "/api/strategy", {}, "a"*32, lambda: (504, {"error": "Timeout"}))
        self.assertEqual(finished(jobs, "owner", one["id"])["httpStatus"], 504)
        two = jobs.start("owner", "/api/strategy", {}, "b"*32, lambda: (200, {}))
        finished(jobs, "owner", two["id"])
        self.assertEqual(len(jobs.jobs), 1)
        with self.assertRaises(ValueError):
            jobs.status("owner", one["id"])

    def test_credentials_and_nonresearch_routes_cannot_be_queued(self):
        jobs = ResearchJobs()
        for route in ("/api/llm-save", "/api/workspace", "/api/auth/login", []):
            with self.subTest(route=route), self.assertRaises(ValueError):
                jobs.start("owner", route, {}, "a"*32, lambda: None)

    def test_completed_job_expires_on_poll(self):
        jobs = ResearchJobs(ttl=1)
        job = jobs.start("owner", "/api/strategy", {}, "a"*32, lambda: (200, {}))
        finished(jobs, "owner", job["id"])
        with patch("nifty100_weekly.nifty100_adapter.research_jobs.monotonic", return_value=time.monotonic()+2):
            with self.assertRaises(ValueError):
                jobs.status("owner", job["id"])
