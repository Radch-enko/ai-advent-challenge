"""The reviewer sends a strict schema while keeping diff validation in the app."""

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from code_assistance.config import load_config
from code_assistance.providers import OpenAIProvider, OpenAIStructuredGenerator
from code_assistance.review_analysis import REVIEW_RESPONSE_SCHEMA, validate_draft


def test_reviewer_requests_structured_output_and_validates_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    class FakeStream:
        def __init__(self, events: list[SimpleNamespace]) -> None:
            self.events = events

        def __enter__(self) -> "FakeStream":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def __iter__(self) -> Iterator[SimpleNamespace]:
            return iter(self.events)

    class FakeResponses:
        def create(self, **kwargs: Any) -> FakeStream:
            captured.update(kwargs)
            output_text = json.dumps(
                {
                    "summary": "Ошибка в коде.",
                    "findings": [
                        {
                            "path": "src/example.py",
                            "line": 1,
                            "side": "RIGHT",
                            "category": "bug",
                            "blocking": True,
                            "body": "Неверное значение.",
                        }
                    ],
                }
            )
            return FakeStream(
                [
                    SimpleNamespace(type="response.created"),
                    SimpleNamespace(
                        type="response.output_text.delta",
                        delta=output_text[:20],
                    ),
                    SimpleNamespace(
                        type="response.output_text.delta",
                        delta=output_text[20:],
                    ),
                    SimpleNamespace(
                        type="response.completed",
                        response=SimpleNamespace(output_text=output_text, status="completed"),
                    ),
                ]
            )

    provider = OpenAIProvider(load_config(tmp_path / "missing.toml"))
    monkeypatch.setattr(provider, "_get_client", lambda: SimpleNamespace(responses=FakeResponses()))
    generator = OpenAIStructuredGenerator(provider, "code_review", REVIEW_RESPONSE_SCHEMA)

    result = generator.generate("review instructions", "PR diff")

    assert captured["text"] == {
        "format": {
            "type": "json_schema",
            "name": "code_review",
            "strict": True,
            "schema": REVIEW_RESPONSE_SCHEMA,
        }
    }
    assert captured["stream"] is True
    assert validate_draft(result, {"src/example.py": "@@ -1 +1 @@\n-old\n+new\n"}).event == (
        "REQUEST_CHANGES"
    )
