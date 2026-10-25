"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from self_healing_platform.app import create_app
from self_healing_platform.config import Settings
from self_healing_platform.db import Base


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.sqlite"


@pytest.fixture()
def settings(db_path: Path) -> Settings:
    return Settings(
        app_env="development",
        database_url=f"sqlite+pysqlite:///{db_path}",
        demo_failure_enabled=False,
        demo_auth_token="",
        remediation_enabled=False,
        remediation_dry_run_only=True,
        remediation_auth_token="",
        ai_summaries_enabled=False,
    )


@pytest.fixture()
def app(settings: Settings):
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    return application


@pytest.fixture()
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def demo_settings(db_path: Path) -> Settings:
    return Settings(
        app_env="demo",
        database_url=f"sqlite+pysqlite:///{db_path}",
        demo_failure_enabled=True,
        demo_auth_token="demo-token-test",
        remediation_enabled=True,
        remediation_dry_run_only=False,
        remediation_auth_token="remediate-token-test",
        ai_summaries_enabled=False,
    )


@pytest.fixture()
def demo_app(demo_settings: Settings):
    application = create_app(demo_settings)
    Base.metadata.create_all(application.state.engine)
    return application


@pytest.fixture()
def demo_client(demo_app) -> Generator[TestClient, None, None]:
    with TestClient(demo_app) as test_client:
        yield test_client
