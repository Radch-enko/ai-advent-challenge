from pathlib import Path
from types import SimpleNamespace

import pytest

from code_assistance.config import load_config
from code_assistance.errors import ProviderError
from code_assistance.models import Chunk, SearchHit
from code_assistance.providers import OpenAIProvider
from code_assistance.service import NO_EVIDENCE_ANSWER, _validate_citations


@pytest.mark.parametrize(
    ("status", "reason", "expected_message"),
    [
        (
            "incomplete",
            "max_output_tokens",
            "stopped generation at a token limit",
        ),
        (
            "incomplete",
            "content_filter",
            "blocked by its content filter",
        ),
    ],
)
def test_empty_openai_responses_explain_safe_completion_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    reason: str,
    expected_message: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-api-key")
    provider = OpenAIProvider(load_config(tmp_path / "config.toml"))
    response = SimpleNamespace(
        output_text="",
        status=status,
        incomplete_details=SimpleNamespace(reason=reason),
    )
    requests: list[dict[str, object]] = []

    class FakeResponses:
        def create(self, **request_arguments: object) -> SimpleNamespace:
            requests.append(request_arguments)
            return response

    monkeypatch.setattr(
        provider,
        "_get_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )

    with pytest.raises(ProviderError, match=expected_message):
        provider.generate("fixture instructions", "fixture question")

    assert len(requests) == 1
    assert "max_output_tokens" not in requests[0]


@pytest.mark.parametrize(
    "answer",
    [
        "Claim with an invented path [docs/product/vision.md:L1-L35].",
        "Claim with combined markers [S1,S2].",
        "Claim with several combined markers [S3,S4,S5].",
    ],
)
def test_noncanonical_or_model_authored_citations_are_rejected(answer: str) -> None:
    hit = SearchHit(
        chunk=Chunk(
            source_path="docs/architecture.md",
            start_line=4,
            end_line=8,
            text="Fixture documentation excerpt.",
        ),
        score=0.9,
    )

    assert _validate_citations(answer, [hit]) == NO_EVIDENCE_ANSWER
