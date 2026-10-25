#!/usr/bin/env python3
"""HTTP smoke test against a running instance (default http://127.0.0.1:8000)."""

from __future__ import annotations

import os
import sys

import httpx

BASE = os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000")


def main() -> int:
    failures = 0
    with httpx.Client(base_url=BASE, timeout=5.0) as client:
        checks = [
            ("GET", "/", 200),
            ("GET", "/health/live", 200),
            ("GET", "/health/ready", 200),
            ("GET", "/api/v1/status", 200),
            ("GET", "/metrics", 200),
        ]
        for method, path, expected in checks:
            response = client.request(method, path)
            ok = response.status_code == expected
            print(f"{'PASS' if ok else 'FAIL'} {method} {path} -> {response.status_code}")
            if not ok:
                failures += 1
        metrics = client.get("/metrics").text
        for name in (
            "http_requests_total",
            "http_request_duration_seconds",
            "application_uptime_seconds",
            "incident_analysis_total",
            "incident_analysis_duration_seconds",
            "demo_failure_events_total",
        ):
            present = name in metrics
            print(f"{'PASS' if present else 'FAIL'} metrics contain {name}")
            if not present:
                failures += 1
        hidden = client.post("/api/v1/demo/failure", json={"mode": "http_500"})
        demo_hidden = hidden.status_code == 404
        print(f"{'PASS' if demo_hidden else 'FAIL'} demo failure disabled -> {hidden.status_code}")
        if not demo_hidden:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
