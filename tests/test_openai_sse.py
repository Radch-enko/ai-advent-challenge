"""Structured Responses API streams retry from the start after a broken stream."""

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, OpenAI

from code_assistance.config import load_config
from code_assistance.providers import OpenAIProvider


def test_structured_response_uses_openai_sdk_sse_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_text = json.dumps({"summary": "Review complete.", "findings": []})
    completed_response = {
        "id": "resp_fixture",
        "created_at": 123456,
        "model": "gpt-5-mini",
        "object": "response",
        "output": [
            {
                "id": "msg_fixture",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": output_text, "annotations": []}],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "status": "completed",
    }
    events = [
        {
            "type": "response.created",
            "sequence_number": 0,
            "response": {
                **completed_response,
                "status": "in_progress",
                "output": [],
            },
        },
        {
            "type": "response.output_text.delta",
            "sequence_number": 1,
            "delta": output_text,
        },
        {
            "type": "response.completed",
            "sequence_number": 2,
            "response": completed_response,
        },
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert payload["stream"] is True
        body = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(respond))
    client = OpenAI(api_key="fixture-api-key", http_client=http_client)
    provider = OpenAIProvider(load_config(tmp_path / "missing.toml"))
    monkeypatch.setattr(provider, "_get_client", lambda: client)

    try:
        result = provider.generate(
            "review instructions",
            "PR diff",
            text_format={"type": "json_schema", "name": "review", "schema": {}},
        )
    finally:
        client.close()

    assert result == output_text


@pytest.mark.parametrize("failure_mode", ["connection_drop", "early_eof"])
def test_structured_response_retries_after_an_incomplete_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    monkeypatch.setattr("code_assistance.http_retry.time.sleep", lambda _: None)
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    final_text = json.dumps({"summary": "Review complete.", "findings": []})

    class FakeStream:
        def __init__(self, events: Iterator[SimpleNamespace]) -> None:
            self.events = events
            self.closed = False

        def __enter__(self) -> "FakeStream":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            self.closed = True

        def __iter__(self) -> Iterator[SimpleNamespace]:
            return self.events

    class FakeResponses:
        calls = 0
        streams: list[FakeStream] = []
        arguments: list[dict[str, Any]] = []

        def create(self, **kwargs: Any) -> FakeStream:
            self.calls += 1
            self.arguments.append(kwargs)
            if self.calls == 1:

                def interrupted() -> Iterator[SimpleNamespace]:
                    yield SimpleNamespace(type="response.output_text.delta", delta="partial")
                    if failure_mode == "connection_drop":
                        raise APIConnectionError(request=request)

                stream = FakeStream(interrupted())
            else:
                stream = FakeStream(
                    iter(
                        [
                            SimpleNamespace(type="response.created"),
                            SimpleNamespace(
                                type="response.completed",
                                response=SimpleNamespace(
                                    output_text=final_text,
                                    status="completed",
                                ),
                            ),
                        ]
                    )
                )
            self.streams.append(stream)
            return stream

    provider = OpenAIProvider(load_config(tmp_path / "missing.toml"), max_retries=1)
    responses = FakeResponses()
    monkeypatch.setattr(provider, "_get_client", lambda: SimpleNamespace(responses=responses))

    result = provider.generate(
        "review instructions",
        "PR diff",
        text_format={"type": "json_schema", "name": "review", "schema": {}},
    )

    assert result == final_text
    assert responses.calls == 2
    assert all(arguments["stream"] is True for arguments in responses.arguments)
    assert all(stream.closed for stream in responses.streams)
