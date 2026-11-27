"""Bounded background research with short, authenticated HTTP polling."""
from contextvars import ContextVar
from hashlib import sha256
import json
from threading import Lock, Thread
from time import monotonic
from uuid import uuid4

ROUTES = {"/api/strategy-builder", "/api/full-catalogue", "/api/research-committee", "/api/model-test"}
_progress = ContextVar("research_progress", default=None)


def progress(stage, **details):
    callback = _progress.get()
    if callback:
        callback(stage, details)


class JobBusy(ValueError):
    pass


class ResearchJobs:
    def __init__(self, capacity=2, retained=32, ttl=3600):
        self.lock = Lock()
        self.jobs = {}
        self.capacity, self.retained, self.ttl = capacity, retained, ttl

    def start(self, owner, route, body, request_id, run):
        if not isinstance(route, str) or route not in ROUTES or not isinstance(body, dict):
            raise ValueError("Choose a supported research operation.")
        if not isinstance(request_id, str) or not 16 <= len(request_id) <= 64 or not request_id.isalnum():
            raise ValueError("Provide a valid research request ID.")
        fingerprint = sha256(json.dumps([route, body], sort_keys=True).encode()).hexdigest()
        with self.lock:
            now = monotonic()
            for key, job in list(self.jobs.items()):
                if job["state"] in ("succeeded", "failed") and now - job["finished"] > self.ttl:
                    del self.jobs[key]
            for job in self.jobs.values():
                if job["owner"] == owner and request_id in job["requestIds"]:
                    if job["fingerprint"] != fingerprint:
                        raise ValueError("This research request ID was already used for different inputs.")
                    return self._view(job)
                if (job["owner"] == owner and job["fingerprint"] == fingerprint
                        and job["state"] in ("queued", "running")):
                    if len(job["requestIds"]) >= 32:
                        raise JobBusy("This research run already has too many duplicate submissions.")
                    job["requestIds"].add(request_id)
                    return self._view(job)
            if sum(job["state"] in ("queued", "running") for job in self.jobs.values()) >= self.capacity:
                raise JobBusy("Research workers are busy. Wait for an active run to finish before starting another.")
            while len(self.jobs) >= self.retained:
                completed = [job for job in self.jobs.values() if job["state"] in ("succeeded", "failed")]
                if not completed:
                    raise JobBusy("Research workers are busy.")
                del self.jobs[min(completed, key=lambda job: job["finished"])["id"]]
            job = dict(id=uuid4().hex, owner=owner, requestIds={request_id}, fingerprint=fingerprint,
                       state="queued", stage="Starting research", started=now, finished=None, details={})
            self.jobs[job["id"]] = job
            Thread(target=self._run, args=(job, run), daemon=True, name="si-research").start()
            return self._view(job)

    def _run(self, job, run):
        def update(stage, details):
            with self.lock:
                job.update(stage=stage, details={**job["details"], **details})
        with self.lock:
            job["state"] = "running"
        token = _progress.set(update)
        try:
            status, result = run()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Research job %s failed", job["id"])
            status, result = 500, {"error": "Research failed. Check the server log.", "requestId": job["id"]}
        finally:
            _progress.reset(token)
        with self.lock:
            job.update(state="succeeded" if status < 400 else "failed", httpStatus=status,
                       result=result, finished=monotonic(), stage="Complete" if status < 400 else "Research stopped")

    def status(self, owner, identifier):
        with self.lock:
            job = self.jobs.get(identifier) if isinstance(identifier, str) else None
            if (job is not None and job["state"] in ("succeeded", "failed")
                    and monotonic() - job["finished"] > self.ttl):
                del self.jobs[identifier]
                job = None
            if job is None or job["owner"] != owner:
                raise ValueError("Research job not found. It may have expired or the server restarted.")
            return self._view(job)

    def _view(self, job):
        result = {key: job[key] for key in ("id", "state", "stage", "details")}
        result["elapsedSeconds"] = round((job["finished"] or monotonic()) - job["started"])
        if job["state"] in ("succeeded", "failed"):
            result.update(httpStatus=job["httpStatus"], result=job["result"])
        return result
