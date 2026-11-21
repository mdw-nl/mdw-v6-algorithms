import pytest

from v6run.profiles import UnknownProfileError, resolve_profile

_ALL_KEYS = ["SERVER_URL", "PORT", "API_PATH", "USERNAME", "PASSWORD", "DATABASE_LABEL", "PRIVATE_KEY_PATH"]


def test_dev_profile_has_working_defaults_with_no_env_vars_set(monkeypatch):
    for key in _ALL_KEYS:
        monkeypatch.delenv(f"V6RUN_DEV_{key}", raising=False)

    profile = resolve_profile("dev")

    assert profile.server_url == "http://localhost"
    assert profile.port == 7601
    assert profile.api_path == "/api"
    assert profile.username == "dev_admin"
    assert profile.database_label == "default"
    assert profile.private_key_path is None


def test_dev_profile_env_vars_override_defaults(monkeypatch):
    monkeypatch.setenv("V6RUN_DEV_USERNAME", "someone_else")
    monkeypatch.setenv("V6RUN_DEV_PORT", "9999")

    profile = resolve_profile("dev")

    assert profile.username == "someone_else"
    assert profile.port == 9999


def test_unknown_profile_without_env_vars_raises_clear_error(monkeypatch):
    for key in ["SERVER_URL", "PORT", "USERNAME", "PASSWORD"]:
        monkeypatch.delenv(f"V6RUN_PROD_{key}", raising=False)

    with pytest.raises(UnknownProfileError, match="V6RUN_PROD_SERVER_URL"):
        resolve_profile("prod")


def test_profile_fully_configured_via_env_vars_has_no_hidden_defaults(monkeypatch):
    monkeypatch.setenv("V6RUN_PROD_SERVER_URL", "https://vantage6.example.org")
    monkeypatch.setenv("V6RUN_PROD_PORT", "443")
    monkeypatch.setenv("V6RUN_PROD_USERNAME", "researcher")
    monkeypatch.setenv("V6RUN_PROD_PASSWORD", "hunter2")
    monkeypatch.setenv("V6RUN_PROD_DATABASE_LABEL", "dataset_main")
    monkeypatch.setenv("V6RUN_PROD_PRIVATE_KEY_PATH", "/keys/org.pem")

    profile = resolve_profile("prod")

    assert profile.server_url == "https://vantage6.example.org"
    assert profile.port == 443
    assert profile.api_path == "/api"  # no override set -- falls back to the one shared default
    assert profile.username == "researcher"
    assert profile.password == "hunter2"
    assert profile.database_label == "dataset_main"
    assert profile.private_key_path == "/keys/org.pem"
