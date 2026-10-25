from pathlib import Path

from fastapi.testclient import TestClient

from self_healing_platform.app import create_app
from self_healing_platform.config import Settings
from self_healing_platform.db import Base


def test_production_hides_demo_even_if_flag_set(tmp_path: Path) -> None:
    settings = Settings(
        app_env="production",
        database_url=f"sqlite+pysqlite:///{tmp_path / 'p.sqlite'}",
        demo_failure_enabled=True,
        demo_auth_token="secret",
        ai_summaries_enabled=False,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/demo/failure",
            json={"mode": "http_500"},
            headers={"X-Demo-Token": "secret"},
        )
        assert response.status_code == 404
        status = client.get("/api/v1/status").json()
        assert status["demo_failure_enabled"] is False
        assert status["ai_summaries_enabled"] is False


def test_rejects_command_like_remediation(demo_client: TestClient) -> None:
    created = demo_client.post(
        "/api/v1/incidents/analyze",
        json={
            "source": "sec",
            "affected_component": "app",
            "symptoms": [],
            "evidence": {"http_5xx_count": 30, "http_request_count": 100},
        },
    )
    incident_id = created.json()["id"]
    response = demo_client.post(
        f"/api/v1/incidents/{incident_id}/remediate",
        json={"action": "rm -rf /", "approved": True, "dry_run": True},
        headers={"X-Remediation-Token": "remediate-token-test"},
    )
    assert response.status_code == 403


def test_oversized_and_invalid_payloads(client: TestClient) -> None:
    huge = client.post(
        "/api/v1/incidents/analyze",
        json={
            "source": "x",
            "affected_component": "y",
            "evidence": {"logs_excerpt": "A" * 5000},
        },
    )
    assert huge.status_code == 422
    invalid = client.post("/api/v1/incidents/analyze", json={"nope": True})
    assert invalid.status_code == 422


def test_logs_excerpt_redacted_in_stored_incident(client: TestClient) -> None:
    created = client.post(
        "/api/v1/incidents/analyze",
        json={
            "source": "logs",
            "affected_component": "app",
            "symptoms": [],
            "evidence": {
                "http_5xx_count": 30,
                "http_request_count": 100,
                "logs_excerpt": "Authorization: Bearer super-secret-token-value",
            },
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert "super-secret-token-value" not in str(body)
    assert "[REDACTED]" in body["evidence"]["logs_excerpt"]


def test_ai_disabled_unless_configured(client: TestClient, monkeypatch) -> None:
    def fail_client(*_args, **_kwargs):
        raise AssertionError("external AI client must not be constructed")

    monkeypatch.setattr("self_healing_platform.ai.httpx.Client", fail_client)
    created = client.post(
        "/api/v1/incidents/analyze",
        json={
            "source": "sec",
            "affected_component": "app",
            "symptoms": [],
            "evidence": {"http_5xx_count": 30, "http_request_count": 100},
        },
    )
    assert created.status_code == 200
    assert created.json()["ai_summary"] is None
    status = client.get("/api/v1/status").json()
    assert status["ai_summaries_enabled"] is False


def test_unapproved_execution_does_not_change_demo_state(demo_client: TestClient) -> None:
    created = demo_client.post(
        "/api/v1/incidents/analyze",
        json={
            "source": "sec",
            "affected_component": "app",
            "symptoms": [],
            "evidence": {},
        },
    )
    incident_id = created.json()["id"]
    assert created.json()["lifecycle_status"] == "Needs investigation"
    response = demo_client.post(
        f"/api/v1/incidents/{incident_id}/remediate",
        json={"action": "simulate_clear_demo_failure", "approved": True, "dry_run": False},
        headers={"X-Remediation-Token": "remediate-token-test"},
    )
    assert response.status_code == 409
