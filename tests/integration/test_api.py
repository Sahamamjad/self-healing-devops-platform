from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from self_healing_platform.app import create_app
from self_healing_platform.config import Settings
from self_healing_platform.db import Base


def test_root_live_ready_status(client: TestClient) -> None:
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["name"] == "self-healing-devops-platform"
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "live"
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    status = client.get("/api/v1/status")
    body = status.json()
    assert status.status_code == 200
    assert "demo_auth_token" not in str(body)
    assert body["database_backend"] == "sqlite"
    assert "X-Request-ID" in status.headers


def test_demo_work_limits(client: TestClient) -> None:
    ok = client.get("/api/v1/demo/work", params={"iterations": 3, "delay_ms": 0})
    assert ok.status_code == 200
    bad = client.get("/api/v1/demo/work", params={"iterations": 5000})
    assert bad.status_code == 422
    assert bad.json()["error"]["request_id"]


def test_metrics_and_request_id(client: TestClient) -> None:
    client.get("/health/live", headers={"X-Request-ID": "req-fixed-1"})
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    text_body = metrics.text
    assert "http_requests_total" in text_body
    assert "application_uptime_seconds" in text_body
    assert "req-fixed-1" not in text_body


def test_analyze_persist_and_get(client: TestClient) -> None:
    created = client.post(
        "/api/v1/incidents/analyze",
        json={
            "source": "prometheus",
            "affected_component": "app",
            "symptoms": ["5xx spike"],
            "evidence": {"http_5xx_count": 25, "http_request_count": 200},
        },
    )
    assert created.status_code == 200
    incident = created.json()
    assert incident["classification"] == "elevated_5xx"
    listed = client.get("/api/v1/incidents", params={"classification": "elevated_5xx"})
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    fetched = client.get(f"/api/v1/incidents/{incident['id']}")
    assert fetched.status_code == 200
    missing = client.get("/api/v1/incidents/does-not-exist")
    assert missing.status_code == 404


def test_readiness_fails_when_database_unavailable(tmp_path: Path) -> None:
    from sqlalchemy import create_engine

    db_file = tmp_path / "gone.sqlite"
    settings = Settings(database_url=f"sqlite+pysqlite:///{db_file}", app_env="development")
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        app.state.engine.dispose()
        app.state.engine = create_engine(
            f"sqlite+pysqlite:///{tmp_path / 'missing-dir' / 'db.sqlite'}",
            future=True,
        )
        ready = client.get("/health/ready")
        live = client.get("/health/live")
        assert live.status_code == 200
        assert ready.status_code == 503
        assert ready.json()["status"] == "not_ready"


def test_ready_reports_missing_schema(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'empty.sqlite'}", app_env="development"
    )
    app = create_app(settings)
    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json()["reason"] == "schema_missing"


def test_incident_persists_across_process_restart(tmp_path: Path) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'persist.sqlite'}"
    settings = Settings(database_url=url, app_env="development")
    first = create_app(settings)
    Base.metadata.create_all(first.state.engine)
    with TestClient(first) as client:
        created = client.post(
            "/api/v1/incidents/analyze",
            json={
                "source": "restart",
                "affected_component": "app",
                "symptoms": ["saved"],
                "evidence": {"http_5xx_count": 25, "http_request_count": 100},
            },
        )
        incident_id = created.json()["id"]
    first.state.engine.dispose()

    second = create_app(settings)
    with TestClient(second) as client:
        fetched = client.get(f"/api/v1/incidents/{incident_id}")
    assert fetched.status_code == 200
    assert fetched.json()["source"] == "restart"
    assert fetched.json()["ai_summary"] is None


def test_invalid_filter_and_oversized_body(client: TestClient) -> None:
    bad_filter = client.get("/api/v1/incidents", params={"severity": "catastrophic"})
    assert bad_filter.status_code == 422
    huge = client.post(
        "/api/v1/incidents/analyze",
        content=b"x" * 70000,
        headers={"Content-Type": "application/json", "Content-Length": "70000"},
    )
    assert huge.status_code == 413


def test_alembic_migration(tmp_path: Path) -> None:
    db_file = tmp_path / "migrated.sqlite"
    settings = Settings(database_url=f"sqlite+pysqlite:///{db_file}")
    settings.ensure_sqlite_parent()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
    app = create_app(settings)
    with app.state.engine.connect() as connection:
        tables = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    names = {row[0] for row in tables}
    assert "incidents" in names
    assert "remediation_audits" in names
    assert "alembic_version" in names
