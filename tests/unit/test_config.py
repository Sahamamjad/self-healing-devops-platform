from self_healing_platform.ai import maybe_summarize
from self_healing_platform.config import Settings


def test_defaults_require_no_secrets() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.port == 8000
    assert settings.demo_failure_enabled is False
    assert settings.ai_summaries_enabled is False
    assert settings.kubernetes_remediation_enabled is False
    assert settings.demo_auth_token == ""


def test_invalid_env_rejected() -> None:
    try:
        Settings(app_env="staging")  # type: ignore[arg-type]
    except Exception as exc:
        assert "app_env" in str(exc).lower() or "literal" in str(exc).lower()
    else:
        raise AssertionError("expected validation error")


def test_production_disables_demo_routes() -> None:
    settings = Settings(app_env="production", demo_failure_enabled=True, demo_auth_token="x")
    assert settings.is_production is True
    assert settings.demo_routes_allowed is False


def test_ai_http_url_is_not_called() -> None:
    settings = Settings(
        _env_file=None,
        ai_summaries_enabled=True,
        ai_api_url="http://127.0.0.1:9/summarize",
        ai_api_token="should-not-be-sent",
    )
    result = maybe_summarize(settings, {"logs_excerpt": "token=super-secret"})
    assert result is not None
    assert result["status"] == "skipped"
    assert result["execution_authority"] is False
    assert "should-not-be-sent" not in str(result)


def test_sqlite_absolute_and_relative_paths() -> None:
    relative = Settings(database_url="sqlite+pysqlite:///./data/app.sqlite")
    assert relative.sqlite_path is not None
    assert relative.sqlite_path.as_posix().endswith("data/app.sqlite")
    absolute = Settings(database_url="sqlite+pysqlite:////data/app.sqlite")
    assert absolute.sqlite_path == type(absolute.sqlite_path)("/data/app.sqlite")
