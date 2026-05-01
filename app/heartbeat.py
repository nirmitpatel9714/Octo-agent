"""
Octo Agent — Heartbeat Monitor
===============================
Background thread that tracks agent health: uptime, API connectivity,
memory usage, and system resource stats.  Stores a rolling log of
heartbeat snapshots in heartbeats.json.
"""
from __future__ import annotations

import json
import os
import platform
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class HeartbeatMonitor:
    """Periodically checks agent health and stores snapshots."""

    DEFAULT_INTERVAL = 30  # seconds between heartbeats

    def __init__(
        self,
        root_path: Path,
        api_key: str = "",
        model: str = "",
        interval: int = DEFAULT_INTERVAL,
        max_history: int = 200,
    ) -> None:
        self.root_path = root_path
        self.api_key = api_key
        self.model = model
        self.interval = interval
        self.max_history = max_history
        self._file = root_path / "heartbeats.json"
        self._start_time = time.time()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._history: List[Dict[str, Any]] = self._load_history()

    # ── persistence ──────────────────────────────────────────────────

    def _load_history(self) -> List[Dict[str, Any]]:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                # Trim to max_history on load to prevent unbounded growth
                return data[-self.max_history:]
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save_history(self) -> None:
        with self._lock:
            data = self._history[-self.max_history:]
            self._file.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )

    # ── snapshot creation ────────────────────────────────────────────

    def _take_snapshot(self) -> Dict[str, Any]:
        import psutil
        process = psutil.Process(os.getpid())

        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "status": "healthy",
            "api_key_configured": bool(self.api_key),
            "model": self.model,
            "system": {
                "platform": platform.system(),
                "python": platform.python_version(),
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_total_mb": round(psutil.virtual_memory().total / 1048576),
                "memory_used_percent": psutil.virtual_memory().percent,
            },
            "process": {
                "pid": os.getpid(),
                "memory_mb": round(process.memory_info().rss / 1048576, 1),
                "threads": process.num_threads(),
            },
        }

        # Check API connectivity
        try:
            import requests
            resp = requests.get(
                "https://openrouter.ai/api/v1/models",
                timeout=5,
            )
            snapshot["api_reachable"] = resp.status_code == 200
        except Exception:
            snapshot["api_reachable"] = False
            snapshot["status"] = "degraded"

        return snapshot

    def _take_snapshot_safe(self) -> Dict[str, Any]:
        """Fallback snapshot if psutil is not installed."""
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "status": "healthy",
            "api_key_configured": bool(self.api_key),
            "model": self.model,
            "system": {
                "platform": platform.system(),
                "python": platform.python_version(),
            },
            "process": {
                "pid": os.getpid(),
            },
        }
        try:
            import requests
            resp = requests.get("https://openrouter.ai/api/v1/models", timeout=5)
            snapshot["api_reachable"] = resp.status_code == 200
        except Exception:
            snapshot["api_reachable"] = False
            snapshot["status"] = "degraded"
        return snapshot

    def beat(self) -> Dict[str, Any]:
        """Take a single heartbeat snapshot and store it."""
        try:
            snap = self._take_snapshot()
        except ImportError:
            snap = self._take_snapshot_safe()

        with self._lock:
            self._history.append(snap)
            if len(self._history) > self.max_history:
                self._history = self._history[-self.max_history:]
        self._save_history()
        return snap

    # ── background loop ──────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self.beat()
            self._stop_event.wait(self.interval)

    def start(self) -> None:
        """Start the background heartbeat thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="heartbeat")
        self._thread.start()

    def stop(self) -> None:
        """Stop the background heartbeat thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    # ── query methods ────────────────────────────────────────────────

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    @property
    def latest(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._history[-1] if self._history else None

    @property
    def history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history)

    @property
    def is_healthy(self) -> bool:
        latest = self.latest
        if not latest:
            return True
        return latest.get("status") == "healthy"
