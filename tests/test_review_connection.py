import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIConnectionError

from code_assistance.config import load_config
from code_assistance.errors import ProviderError
from code_assistance.providers import OpenAIProvider
from code_assistance.review_service import ReviewService
from code_assistance.review_state import ReviewJob, ReviewJobStore


def test_openai_connection_check_calls_models_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-api-key")
    calls = 0

    class FakeModels:
        def list(self) -> object:
            nonlocal calls
            calls += 1
            return object()

    provider = OpenAIProvider(load_config(tmp_path / "missing.toml"))
    monkeypatch.setattr(provider, "_get_client", lambda: SimpleNamespace(models=FakeModels()))

    provider.check_connection()

    assert calls == 1


def test_connection_check_failure_stops_review_before_github_access(tmp_path: Path) -> None:
    events: list[str] = []

    def connection_check() -> None:
        events.append("openai")
        raise ProviderError("OpenAI is unavailable.")

    def github_factory(_: int) -> Any:
        events.append("github")
        raise AssertionError("GitHub must not be contacted before the OpenAI preflight succeeds.")

    service = ReviewService(
        github_factory,
        analyzer=object(),  # type: ignore[arg-type]
        store=ReviewJobStore(tmp_path / "jobs.sqlite3"),
        max_file_bytes=1024,
        connection_check=connection_check,
    )

    with pytest.raises(ProviderError, match="unavailable"):
        service.process(ReviewJob(12, 34, "owner/project", 5, "b" * 40, "a" * 40))

    assert events == ["openai"]


def test_openai_connection_check_retries_transient_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-api-key")
    monkeypatch.setattr("code_assistance.http_retry.time.sleep", lambda _: None)
    request = httpx.Request("GET", "https://api.openai.com/v1/models")

    class FlakyModels:
        calls = 0

        def list(self) -> object:
            self.calls += 1
            if self.calls == 1:
                raise APIConnectionError(request=request)
            return object()

    provider = OpenAIProvider(load_config(tmp_path / "missing.toml"), max_retries=1)
    models = FlakyModels()
    monkeypatch.setattr(provider, "_get_client", lambda: SimpleNamespace(models=models))

    provider.check_connection()

    assert models.calls == 2


def test_openai_retries_log_transport_cause_and_redact_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("code_assistance.http_retry.time.sleep", lambda _: None)
    provider = OpenAIProvider(load_config(tmp_path / "missing.toml"), max_retries=1)
    request = httpx.Request(
        "POST",
        "https://api.openai.com/v1/responses?api_key=query-secret",
    )

    def fail_with_transport_error() -> None:
        try:
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response; api_key=body-secret"
            )
        except httpx.RemoteProtocolError as cause:
            raise APIConnectionError(request=request) from cause

    with caplog.at_level(logging.WARNING, logger="code_assistance.providers"):
        with pytest.raises(APIConnectionError):
            provider._request("structured response", fail_with_transport_error)

    assert "request=POST /v1/responses" in caplog.text
    assert "httpx.RemoteProtocolError: Server disconnected without sending a response" in (
        caplog.text
    )
    assert "api_key=<redacted>" in caplog.text
    assert "query-secret" not in caplog.text
    assert "body-secret" not in caplog.text
    assert "attempt_duration=" in caplog.text
    assert "HTTP operation exhausted retries" in caplog.text
