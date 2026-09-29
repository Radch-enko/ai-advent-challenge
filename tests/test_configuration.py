from __future__ import annotations

from copia.common.configuration import get_settings


def test_storage_overrides_keep_existing_path_precedence(monkeypatch, tmp_path) -> None:
    data_root = tmp_path / "data"
    sessions = tmp_path / "custom-sessions"
    invariants = tmp_path / "custom-invariants.json"
    monkeypatch.setenv("COPIA_DATA_ROOT", str(data_root))
    monkeypatch.setenv("COPIA_SESSIONS_PATH", str(sessions))
    monkeypatch.setenv("COPIA_INVARIANTS_PATH", str(invariants))

    settings = get_settings()

    assert settings.sessions_path == sessions
    assert settings.invariants_path == invariants
    assert settings.memory_path == data_root / "memory"
    assert settings.mcp_connections_path == data_root / "mcp_connections.json"


def test_default_invariants_path_tracks_custom_sessions_path(monkeypatch, tmp_path) -> None:
    sessions = tmp_path / "custom-sessions"
    monkeypatch.setenv("COPIA_SESSIONS_PATH", str(sessions))
    monkeypatch.delenv("COPIA_INVARIANTS_PATH", raising=False)

    assert get_settings().invariants_path == tmp_path / "invariants.json"


def test_boolean_flags_keep_false_only_disable_semantics(monkeypatch) -> None:
    monkeypatch.setenv("COPIA_ALLOW_LOCAL_MCP", "0")
    monkeypatch.setenv("COPIA_OTEL_ENABLED", "True")

    settings = get_settings()

    assert settings.allow_local_mcp is True
    assert settings.otel_enabled is True

    monkeypatch.setenv("COPIA_ALLOW_LOCAL_MCP", "false")
    assert get_settings().allow_local_mcp is False


def test_provider_credentials_use_secret_type(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-value")

    credential = get_settings().openai_api_key

    assert credential is not None
    assert credential.get_secret_value() == "test-secret-value"
    assert str(credential) != "test-secret-value"
