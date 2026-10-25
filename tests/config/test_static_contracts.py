"""Static checks for deployment contracts. External CLIs are optional."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path) -> object:
    return yaml.safe_load(path.read_text())


def test_compose_and_prometheus_targets_agree() -> None:
    compose = _load(ROOT / "compose.yaml")
    assert isinstance(compose, dict)
    services = compose["services"]
    assert "app" in services
    assert "prometheus" in services
    assert "grafana" in services
    assert services["app"]["ports"] == ["8000:8000"]
    prom = _load(ROOT / "deploy/monitoring/prometheus/prometheus.compose.yml")
    assert isinstance(prom, dict)
    targets = prom["scrape_configs"][0]["static_configs"][0]["targets"]
    assert targets == ["app:8000"]
    assert prom["scrape_configs"][0]["metrics_path"] == "/metrics"
    rules = _load(ROOT / "deploy/monitoring/prometheus/rules.yml")
    assert isinstance(rules, dict)
    expressions = " ".join(rule["expr"] for group in rules["groups"] for rule in group["rules"])
    for metric in ("up", "http_requests_total", "http_request_duration_seconds_bucket"):
        assert metric in expressions
    assert "clamp_min" in expressions


def test_kubernetes_scrape_uses_cluster_dns_not_compose() -> None:
    text = (ROOT / "deploy/monitoring/prometheus/prometheus.kubernetes.yml").read_text()
    assert "self-healing-platform" in text
    assert "app:8000" not in text
    assert "namespace: self-healing" in text or "self-healing" in text


def test_grafana_datasource_matches_compose_prometheus() -> None:
    datasource = _load(ROOT / "deploy/monitoring/grafana/provisioning/datasources/datasource.yml")
    assert isinstance(datasource, dict)
    item = datasource["datasources"][0]
    assert item["url"] == "http://prometheus:9090"
    assert item["uid"] == "prometheus"
    dashboard = (
        ROOT / "deploy/monitoring/grafana/provisioning/dashboards/json/self-healing-overview.json"
    ).read_text()
    for metric in (
        "http_requests_total",
        "http_request_duration_seconds_bucket",
        "application_uptime_seconds",
        "incident_analysis_total",
        'up{job=\\"self-healing-app\\"}',
    ):
        assert metric in dashboard


def test_argocd_points_at_helm_chart() -> None:
    app = _load(ROOT / "deploy/argocd/application.yaml")
    assert isinstance(app, dict)
    source = app["spec"]["source"]
    assert source["path"] == "deploy/helm/self-healing-platform"
    assert "automated" not in app["spec"].get("syncPolicy", {})
    assert "REPLACE_OWNER" in source["repoURL"]


def test_helm_chart_metadata() -> None:
    chart = _load(ROOT / "deploy/helm/self-healing-platform/Chart.yaml")
    assert isinstance(chart, dict)
    assert chart["apiVersion"] == "v2"
    assert chart["name"] == "self-healing-platform"
    values = _load(ROOT / "deploy/helm/self-healing-platform/values.yaml")
    assert isinstance(values, dict)
    assert values["replicaCount"] == 1
    assert values["service"]["port"] == 8000
    assert values["image"]["tag"] != "latest"


def test_workflows_pin_actions_by_sha() -> None:
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        text = path.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if "uses:" in stripped and "@" in stripped:
                assert "@" in stripped
                sha = stripped.split("@", 1)[1].split()[0]
                assert len(sha) == 40
                int(sha, 16)


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
def test_helm_lint() -> None:
    chart = ROOT / "deploy/helm/self-healing-platform"
    completed = subprocess.run(
        ["helm", "lint", str(chart)], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform is not installed")
def test_terraform_validate() -> None:
    directory = ROOT / "terraform/aws"
    init = subprocess.run(
        ["terraform", "init", "-backend=false", "-input=false"],
        cwd=directory,
        check=False,
        capture_output=True,
        text=True,
    )
    assert init.returncode == 0, init.stdout + init.stderr
    validate = subprocess.run(
        ["terraform", "validate"],
        cwd=directory,
        check=False,
        capture_output=True,
        text=True,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
