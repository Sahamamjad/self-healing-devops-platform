from self_healing_platform.metrics import AppMetrics


def test_metrics_render_contains_required_names() -> None:
    metrics = AppMetrics()
    metrics.observe_request("GET", "/health/live", 200, 0.01)
    metrics.incident_analysis_total.labels(outcome="classified").inc()
    metrics.demo_failure_events_total.labels(mode="http_500").inc()
    body = metrics.render().decode("utf-8")
    for name in (
        "http_requests_total",
        "http_request_duration_seconds",
        "application_uptime_seconds",
        "incident_analysis_total",
        "incident_analysis_duration_seconds",
        "demo_failure_events_total",
    ):
        assert name in body
    assert 'route="/health/live"' in body
    assert "incident-123" not in body
