"""
Octo Agent — Cron Job Scheduler
================================
Manages scheduled tasks that run agent prompts at defined intervals.
Jobs are persisted in cron_jobs.json and executed via a background
scheduler thread.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class CronJob:
    """A single scheduled job definition."""

    def __init__(
        self,
        job_id: str,
        name: str,
        schedule: str,
        prompt: str,
        enabled: bool = True,
        created_at: str = "",
    ) -> None:
        self.job_id = job_id
        self.name = name
        self.schedule = schedule      # simplified: "every Xs", "every Xm", "every Xh"
        self.prompt = prompt
        self.enabled = enabled
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.last_run: Optional[str] = None
        self.run_count: int = 0
        self.last_result: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "schedule": self.schedule,
            "prompt": self.prompt,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "last_result": self.last_result,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CronJob":
        job = cls(
            job_id=data["job_id"],
            name=data["name"],
            schedule=data["schedule"],
            prompt=data["prompt"],
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", ""),
        )
        job.last_run = data.get("last_run")
        job.run_count = data.get("run_count", 0)
        job.last_result = data.get("last_result")
        return job

    def interval_seconds(self) -> int:
        """Parse the simplified schedule string into seconds."""
        s = self.schedule.strip().lower()
        if s.startswith("every "):
            s = s[6:].strip()

        if s.endswith("s"):
            return max(int(s[:-1]), 10)
        elif s.endswith("m"):
            return int(s[:-1]) * 60
        elif s.endswith("h"):
            return int(s[:-1]) * 3600
        elif s.endswith("d"):
            return int(s[:-1]) * 86400
        else:
            # Assume seconds
            try:
                return max(int(s), 10)
            except ValueError:
                return 300  # default 5 min


class CronScheduler:
    """Manages a collection of cron jobs with a background executor."""

    def __init__(
        self,
        root_path: Path,
        executor: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.root_path = root_path
        self._file = root_path / "cron_jobs.json"
        self._executor = executor  # callback: (prompt) -> result
        self._jobs: Dict[str, CronJob] = {}
        self._timers: Dict[str, float] = {}  # job_id -> next_run_time
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._load()

    # ── persistence ──────────────────────────────────────────────────

    def _load(self) -> None:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                for entry in data:
                    job = CronJob.from_dict(entry)
                    self._jobs[job.job_id] = job
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        with self._lock:
            data = [j.to_dict() for j in self._jobs.values()]
            self._file.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )

    # ── job management ───────────────────────────────────────────────

    def add_job(self, name: str, schedule: str, prompt: str) -> CronJob:
        """Add a new cron job."""
        job = CronJob(
            job_id=uuid.uuid4().hex[:8],
            name=name,
            schedule=schedule,
            prompt=prompt,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._timers[job.job_id] = time.time() + job.interval_seconds()
        self._save()
        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove a cron job by ID."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                self._timers.pop(job_id, None)
                self._save()
                return True
        return False

    def toggle_job(self, job_id: str) -> Optional[bool]:
        """Toggle a job's enabled state. Returns new state or None if not found."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.enabled = not job.enabled
                self._save()
                return job.enabled
        return None

    def list_jobs(self) -> List[CronJob]:
        """Return all jobs."""
        with self._lock:
            return list(self._jobs.values())

    def get_job(self, job_id: str) -> Optional[CronJob]:
        with self._lock:
            return self._jobs.get(job_id)

    # ── executor ─────────────────────────────────────────────────────

    def set_executor(self, executor: Callable[[str], str]) -> None:
        """Set the callback that runs a prompt and returns a result."""
        self._executor = executor

    def _run_job(self, job: CronJob) -> None:
        """Execute a single job."""
        if not self._executor:
            return
        try:
            result = self._executor(job.prompt)
            job.last_result = result[:500] if result else "(no output)"
        except Exception as exc:
            job.last_result = f"Error: {exc}"
        job.last_run = datetime.now(timezone.utc).isoformat()
        job.run_count += 1
        self._save()

    # ── scheduler loop ───────────────────────────────────────────────

    def _loop(self) -> None:
        # Initialize timers for any jobs that don't have one
        now = time.time()
        for job_id, job in self._jobs.items():
            if job_id not in self._timers:
                self._timers[job_id] = now + job.interval_seconds()

        while not self._stop_event.is_set():
            now = time.time()
            with self._lock:
                due_jobs = [
                    (jid, job)
                    for jid, job in self._jobs.items()
                    if job.enabled and self._timers.get(jid, 0) <= now
                ]

            for jid, job in due_jobs:
                self._run_job(job)
                with self._lock:
                    self._timers[jid] = time.time() + job.interval_seconds()

            self._stop_event.wait(5)  # check every 5 seconds

    def start(self) -> None:
        """Start the background scheduler."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cron-scheduler")
        self._thread.start()

    def stop(self) -> None:
        """Stop the background scheduler."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
