from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from openai import AuthenticationError, RateLimitError

from code_assistance.config import load_config
from code_assistance.errors import ConfigurationError, ProviderError
from code_assistance.providers import OpenAIProvider


@pytest.mark.parametrize(
    ("error_type", "expected_message"),
    [
        (AuthenticationError, "OpenAI rejected the API key"),
        (RateLimitError, "OpenAI rate limit reached"),
    ],
)
def test_openai_provider_sanitizes_authentication_and_rate_limit_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
    expected_message: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-api-key")
    provider = OpenAIProvider(
        load_config(tmp_path / "config.toml"),
        env_file=tmp_path / ".env",
    )
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(401, request=request)

    class FailingResponses:
        def create(self, **request_arguments: object) -> None:
            del request_arguments
            raise error_type(
                "fixture secret error detail",
                response=response,
                body={"message": "fixture secret body"},
            )

    monkeypatch.setattr(
        provider, "_get_client", lambda: SimpleNamespace(responses=FailingResponses())
    )

    with pytest.raises(ProviderError) as error:
        provider.generate("fixture instructions", "fixture question")

    assert expected_message in str(error.value)
    assert "fixture secret" not in str(error.value)


def test_openai_provider_requires_api_key_from_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIProvider(
        load_config(tmp_path / "config.toml"),
        env_file=tmp_path / ".env",
    )

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is not set"):
        provider.embed(["invented documentation"])
