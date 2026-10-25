"""Bounded, in-memory demo failure simulation. Does not affect liveness."""

from __future__ import annotations

import threading
import time

from self_healing_platform.schemas import DemoMode


class DemoFailureController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = False
        self._mode: DemoMode | None = None
        self._until_monotonic = 0.0
        self._remaining_requests = 0
        self._incident_id: str | None = None

    def activate(
        self,
        mode: DemoMode,
        duration_seconds: int,
        max_requests: int,
        incident_id: str,
    ) -> dict[str, object]:
        with self._lock:
            self._enabled = True
            self._mode = mode
            self._until_monotonic = time.monotonic() + duration_seconds
            self._remaining_requests = max_requests
            self._incident_id = incident_id
            return self._status_unlocked()

    def deactivate(self) -> dict[str, object]:
        with self._lock:
            self._clear()
            return self._status_unlocked()

    def status(self) -> dict[str, object]:
        with self._lock:
            self._expire_if_needed()
            return self._status_unlocked()

    def consume_for_path(self, path: str) -> DemoMode | None:
        """Return a failure mode for this request, or None.

        Health endpoints are never affected.
        """
        # Keep probes, metrics, and the incident API usable so an operator can
        # inspect and clear a simulation. Other routes, including /api/v1/status,
        # show the injected failure.
        if path.startswith("/health/") or path in {"/metrics", "/api/v1/demo/failure"}:
            return None
        if path == "/api/v1/incidents" or path.startswith("/api/v1/incidents/"):
            return None
        with self._lock:
            self._expire_if_needed()
            if not self._enabled or self._mode is None:
                return None
            if self._mode == "inject_latency" and not path.startswith("/api/v1/demo/work"):
                return None
            if self._remaining_requests <= 0:
                self._clear()
                return None
            self._remaining_requests -= 1
            mode = self._mode
            if self._remaining_requests <= 0:
                self._clear()
            return mode

    def _clear(self) -> None:
        self._enabled = False
        self._mode = None
        self._until_monotonic = 0.0
        self._remaining_requests = 0
        self._incident_id = None

    def _expire_if_needed(self) -> None:
        if self._enabled and time.monotonic() >= self._until_monotonic:
            self._clear()

    def _status_unlocked(self) -> dict[str, object]:
        remaining = max(0.0, self._until_monotonic - time.monotonic()) if self._enabled else 0.0
        return {
            "enabled": self._enabled,
            "mode": self._mode,
            "remaining_seconds": remaining,
            "remaining_requests": self._remaining_requests if self._enabled else 0,
            "incident_id": self._incident_id,
        }
