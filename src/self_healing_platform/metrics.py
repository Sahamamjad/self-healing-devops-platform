"""Bounded Prometheus metrics with a dedicated registry per app instance."""

from __future__ import annotations

import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

CONTENT_TYPE = CONTENT_TYPE_LATEST

DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class AppMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.started_at = time.monotonic()
        self.http_requests_total = Counter(
            "http_requests_total",
            "Count of HTTP requests handled by the application.",
            labelnames=("method", "route", "status"),
            registry=self.registry,
        )
        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds.",
            labelnames=("method", "route"),
            buckets=DURATION_BUCKETS,
            registry=self.registry,
        )
        self.application_uptime_seconds = Gauge(
            "application_uptime_seconds",
            "Process uptime in seconds.",
            registry=self.registry,
        )
        self.incident_analysis_total = Counter(
            "incident_analysis_total",
            "Incident analysis runs by outcome.",
            labelnames=("outcome",),
            registry=self.registry,
        )
        self.incident_analysis_duration_seconds = Histogram(
            "incident_analysis_duration_seconds",
            "Incident analysis duration in seconds.",
            buckets=DURATION_BUCKETS,
            registry=self.registry,
        )
        self.demo_failure_events_total = Counter(
            "demo_failure_events_total",
            "Explicitly enabled demo failure simulations.",
            labelnames=("mode",),
            registry=self.registry,
        )

    def observe_request(self, method: str, route: str, status: int, duration: float) -> None:
        self.http_requests_total.labels(method=method, route=route, status=str(status)).inc()
        self.http_request_duration_seconds.labels(method=method, route=route).observe(duration)
        self.application_uptime_seconds.set(time.monotonic() - self.started_at)

    def render(self) -> bytes:
        self.application_uptime_seconds.set(time.monotonic() - self.started_at)
        return generate_latest(self.registry)
