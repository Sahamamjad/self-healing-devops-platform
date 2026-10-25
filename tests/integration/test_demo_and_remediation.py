from fastapi.testclient import TestClient


def test_demo_failure_disabled_by_default(client: TestClient) -> None:
    response = client.post("/api/v1/demo/failure", json={"mode": "http_500", "duration_seconds": 5})
    assert response.status_code == 404


def test_demo_failure_requires_token_and_does_not_break_health(demo_client: TestClient) -> None:
    denied = demo_client.post(
        "/api/v1/demo/failure", json={"mode": "http_500", "duration_seconds": 5}
    )
    assert denied.status_code == 401
    enabled = demo_client.post(
        "/api/v1/demo/failure",
        json={"mode": "http_500", "duration_seconds": 30, "max_requests": 5},
        headers={"X-Demo-Token": "demo-token-test"},
    )
    assert enabled.status_code == 200
    incident_id = enabled.json()["incident_id"]
    assert incident_id
    failed = demo_client.get("/api/v1/status")
    assert failed.status_code == 500
    live = demo_client.get("/health/live")
    ready = demo_client.get("/health/ready")
    assert live.status_code == 200
    assert ready.status_code == 200


def test_remediation_dry_run_and_auth(demo_client: TestClient) -> None:
    analyzed = demo_client.post(
        "/api/v1/incidents/analyze",
        json={
            "source": "operator",
            "affected_component": "app",
            "symptoms": ["demo"],
            "evidence": {"http_5xx_count": 30, "http_request_count": 100},
        },
    )
    incident_id = analyzed.json()["id"]
    unauth = demo_client.post(
        f"/api/v1/incidents/{incident_id}/remediate",
        json={"action": "simulate_clear_demo_failure", "approved": True, "dry_run": True},
    )
    assert unauth.status_code == 401
    dry = demo_client.post(
        f"/api/v1/incidents/{incident_id}/remediate",
        json={"action": "simulate_clear_demo_failure", "approved": True, "dry_run": True},
        headers={"X-Remediation-Token": "remediate-token-test"},
    )
    assert dry.status_code == 200
    body = dry.json()
    assert body["dry_run"] is True
    assert body["detail"]["modifies_infrastructure"] is False
    fetched = demo_client.get(f"/api/v1/incidents/{incident_id}")
    assert fetched.json()["lifecycle_status"] == "Approved"


def test_live_simulated_remediation_clears_demo(demo_client: TestClient) -> None:
    started = demo_client.post(
        "/api/v1/demo/failure",
        json={"mode": "http_503", "duration_seconds": 30, "max_requests": 20},
        headers={"X-Demo-Token": "demo-token-test"},
    )
    incident_id = started.json()["incident_id"]
    executed = demo_client.post(
        f"/api/v1/incidents/{incident_id}/remediate",
        json={
            "action": "simulate_clear_demo_failure",
            "approved": True,
            "dry_run": False,
        },
        headers={"X-Remediation-Token": "remediate-token-test"},
    )
    assert executed.status_code == 200
    assert executed.json()["dry_run"] is False
    status = demo_client.get("/api/v1/status")
    assert status.status_code == 200
    incident = demo_client.get(f"/api/v1/incidents/{incident_id}").json()
    assert incident["lifecycle_status"] == "Verified"
