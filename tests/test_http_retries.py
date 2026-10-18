"""Transient HTTP failures are retried without duplicating published reviews."""

import io
import logging
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import httpx
import pytest
from openai import APIConnectionError

from code_assistance.config import load_config
from code_assistance.github_app import GitHubAppClient, GitHubAppError, GitHubAppSettings
from code_assistance.http_retry import RetryPolicy
from code_assistance.providers import OpenAIProvider


def test_openai_connection_failure_retries_then_returns_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-api-key")
    monkeypatch.setattr("code_assistance.http_retry.time.sleep", lambda _: None)
    provider = OpenAIProvider(load_config(tmp_path / "config.toml"), max_retries=2)
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")

    class FlakyResponses:
        calls = 0

        def create(self, **arguments: object) -> SimpleNamespace:
            del arguments
            self.calls += 1
            if self.calls < 3:
                raise APIConnectionError(request=request)
            return SimpleNamespace(output_text="Recovered")

    responses = FlakyResponses()
    monkeypatch.setattr(provider, "_get_client", lambda: SimpleNamespace(responses=responses))

    with caplog.at_level(logging.WARNING):
        assert provider.generate("instructions", "prompt") == "Recovered"

    assert responses.calls == 3
    assert caplog.messages == [message for message in caplog.messages if "retry=" in message]
    assert len(caplog.messages) == 2


def _settings(tmp_path: Path) -> GitHubAppSettings:
    return GitHubAppSettings(
        "123",
        tmp_path / "unused.pem",
        "secret",
        "owner",
        tmp_path / "data",
        8080,
        RetryPolicy(max_attempts=3, base_delay_seconds=0.1),
    )


def test_github_get_retries_network_failure_but_not_permanent_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("code_assistance.http_retry.time.sleep", lambda _: None)
    client = GitHubAppClient(_settings(tmp_path), 1)
    responses: list[object] = [URLError("offline"), io.BytesIO(b'{"ok": true}')]

    def flaky_urlopen(request: object, timeout: int) -> io.BytesIO:
        del request, timeout
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        assert isinstance(value, io.BytesIO)
        return value

    monkeypatch.setattr("code_assistance.github_app.urlopen", flaky_urlopen)
    assert client._request("GET", "/fixture", auth="token") == {"ok": True}
    assert not responses

    calls = 0

    def missing_urlopen(request: object, timeout: int) -> io.BytesIO:
        nonlocal calls
        del request, timeout
        calls += 1
        raise HTTPError("https://api.github.com/missing", 404, "missing", None, None)

    monkeypatch.setattr("code_assistance.github_app.urlopen", missing_urlopen)
    with pytest.raises(GitHubAppError, match="HTTP 404"):
        client._request("GET", "/missing", auth="token")
    assert calls == 1


def test_publish_retry_reconciles_an_ambiguous_success_before_repeating_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("code_assistance.http_retry.time.sleep", lambda _: None)
    client = GitHubAppClient(_settings(tmp_path), 1)
    monkeypatch.setattr(client, "_installation_token", lambda: "token")
    post_calls = 0

    def disconnected_urlopen(request: object, timeout: int) -> io.BytesIO:
        nonlocal post_calls
        del request, timeout
        post_calls += 1
        raise URLError("response was lost")

    monkeypatch.setattr("code_assistance.github_app.urlopen", disconnected_urlopen)
    monkeypatch.setattr(client, "review_id_for_marker", lambda *args: 73)
    marker = "<!-- code-assistance-reviewer:1:2:head:base -->"

    review_id = client.create_review(
        "owner/repo",
        2,
        {"body": f"Summary\n\n{marker}", "event": "APPROVE", "comments": []},
    )

    assert review_id == 73
    assert post_calls == 1
