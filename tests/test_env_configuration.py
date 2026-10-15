from pathlib import Path

import pytest

from code_assistance.config import api_key_from_environment, default_env_file, load_config
from code_assistance.errors import ConfigurationError
from code_assistance.providers import OpenAIProvider


def test_api_key_is_loaded_from_project_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OTHER_SETTING=ignored\n"
        "# fixture only\n"
        'export OPENAI_API_KEY = "fixture-dotenv-key" # comment\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert api_key_from_environment(env_file) == "fixture-dotenv-key"


def test_process_environment_takes_precedence_over_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=fixture-file-key\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-process-key")

    assert api_key_from_environment(env_file) == "fixture-process-key"


def test_openai_provider_uses_key_from_injected_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=fixture-provider-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured_arguments: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **arguments: object) -> None:
            captured_arguments.update(arguments)

    monkeypatch.setattr("code_assistance.providers.OpenAI", FakeOpenAI)
    provider = OpenAIProvider(load_config(tmp_path / "config.toml"), env_file=env_file)

    provider._get_client()

    assert captured_arguments["api_key"] == "fixture-provider-key"


def test_missing_key_error_does_not_include_env_file_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER_SETTING=fixture-secret-value\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ConfigurationError) as error:
        api_key_from_environment(env_file)

    assert "OPENAI_API_KEY is not set" in str(error.value)
    assert "fixture-secret-value" not in str(error.value)


def test_default_env_file_is_anchored_to_code_assistance_source() -> None:
    assert default_env_file() == Path(__file__).resolve().parents[1] / ".env"
