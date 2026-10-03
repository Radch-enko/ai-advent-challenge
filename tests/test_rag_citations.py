from __future__ import annotations

import pytest

from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.document_indexing.application.rag_citations import (
    RAG_CITATION_WARNING,
    RagCitationValidationError,
    complete_with_citation_recovery,
    strip_rag_citation_warning,
    validate_rag_response,
)
from copia.document_indexing.domain.models.rag_retrieval_result import RagRetrievalResult
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_name import ProviderName
from copia.sessions.domain.models.chat_message import ChatMessage


def make_result(text: str = "A fictional handbook says a blue kite is stored in locker 4."):
    source = KnowledgeSource(
        chunk_id="handbook-4",
        source="fictional-handbook.md",
        title="Fictional Handbook",
        section="Storage",
        similarity_score=0.72,
        selected_for_context=True,
    )
    return RagRetrievalResult(
        context_chunks=[RetrievedChunk(text=text, source=source)],
        filtered_sources=[source],
    )


def make_response(answer: str, *, chunk_id: str = "handbook-4", quote: str = "blue kite"):
    data = {"answer": answer, "citations": [{"chunk_id": chunk_id, "quote": quote}]}
    return LLMResponse(
        content="provider JSON must not be returned as the answer",
        structured_data=data,
        provider=ProviderName.OPENAI,
        model="test-model",
    )


@pytest.mark.parametrize(
    "response",
    [
        make_response("   "),
        make_response("The kite is blue: blue kite", chunk_id="unknown-chunk"),
        make_response("The kite is blue: missing phrase", quote="missing phrase"),
        make_response("The kite is blue", quote="blue kite"),
    ],
    ids=["empty-answer", "unknown-chunk-id", "quote-not-in-chunk", "quote-not-in-answer"],
)
def test_invalid_citations_are_rejected(response: LLMResponse) -> None:
    with pytest.raises(RagCitationValidationError):
        validate_rag_response(response, make_result())


def test_valid_citation_uses_retrieved_source_and_plain_answer() -> None:
    answer = 'The blue kite is in locker 4: "blue kite is stored in locker 4".'
    response = make_response(answer, quote="blue kite is stored in locker 4")

    validated, sources = validate_rag_response(response, make_result())

    assert validated.content == answer
    assert validated.structured_data == response.structured_data
    assert len(sources) == 1
    assert sources[0].model_dump(mode="json") == {
        "chunk_id": "handbook-4",
        "source": "fictional-handbook.md",
        "title": "Fictional Handbook",
        "section": "Storage",
        "similarity_score": 0.72,
        "selected_for_context": True,
        "quote": "blue kite is stored in locker 4",
    }


def test_invalid_first_response_is_retried_and_only_verified_answer_returns() -> None:
    result = make_result()
    answers = [
        make_response("The kite is blue.", quote="blue kite"),
        make_response(
            'The kite is in locker 4: "blue kite is stored in locker 4".',
            quote="blue kite is stored in locker 4",
        ),
    ]
    configs = []
    request_messages = []

    def complete(messages, config):
        configs.append(config)
        request_messages.append(messages)
        return answers.pop(0)

    response, sources = complete_with_citation_recovery(
        complete,
        [ChatMessage(role="user", content="Where is the kite?")],
        LLMConfig(provider=ProviderName.OPENAI, model="test-model"),
        result,
    )

    assert response.content == 'The kite is in locker 4: "blue kite is stored in locker 4".'
    assert sources[0].quote == "blue kite is stored in locker 4"
    assert len(configs) == 2
    assert configs[0].structured_output is not None
    assert configs[0].structured_output.json_schema["required"] == ["answer", "citations"]
    assert "citation validation" in request_messages[1][-1].content


def test_second_invalid_response_returns_answer_with_warning_and_safe_source() -> None:
    responses = [make_response("unverified"), make_response("still unverified")]
    calls = 0

    def complete(messages, config):
        nonlocal calls
        calls += 1
        return responses.pop(0)

    response, sources = complete_with_citation_recovery(
        complete,
        [ChatMessage(role="user", content="Where is the kite?")],
        LLMConfig(provider=ProviderName.OPENAI, model="test-model"),
        make_result(),
    )

    assert calls == 2
    assert response.content == f"{RAG_CITATION_WARNING}\n\nstill unverified"
    assert len(sources) == 1
    assert sources[0].chunk_id == "handbook-4"
    assert sources[0].quote == "blue kite"


def test_second_invalid_response_without_source_match_returns_answer_without_sources() -> None:
    responses = [
        make_response("Unverified answer", chunk_id="unknown-chunk", quote="invented quote"),
        make_response("Last available answer", chunk_id="unknown-chunk", quote="invented quote"),
    ]

    def complete(messages, config):
        return responses.pop(0)

    response, sources = complete_with_citation_recovery(
        complete,
        [ChatMessage(role="user", content="Where is the kite?")],
        LLMConfig(provider=ProviderName.OPENAI, model="test-model"),
        make_result(),
    )

    assert response.content == f"{RAG_CITATION_WARNING}\n\nLast available answer"
    assert sources == []


def test_report_validation_can_ignore_the_display_warning_prefix() -> None:
    report = "## Итоговый ответ\n\nDone\n\n### Детали\n\nDetails\n\n### Ограничения\n\nНет"

    assert strip_rag_citation_warning(f"{RAG_CITATION_WARNING}\n\n{report}") == report


@pytest.mark.parametrize(
    ("question", "source_text", "quote", "answer"),
    [
        (
            "When does the Moon Kiosk open?",
            "The Moon Kiosk opens at 06:15 on weekdays.",
            "opens at 06:15 on weekdays",
            'The Moon Kiosk opens at 06:15: "opens at 06:15 on weekdays".',
        ),
        (
            "Where does the Cloud Tram stop?",
            "The Cloud Tram stops beside the blue fountain.",
            "stops beside the blue fountain",
            'It stops by the fountain: "stops beside the blue fountain".',
        ),
        (
            "Which color is the archive door?",
            "The archive door is painted green for the story exercise.",
            "door is painted green",
            'The archive door is green: "door is painted green".',
        ),
        (
            "How many bells ring at noon?",
            "At noon, exactly three small bells ring in the toy village.",
            "exactly three small bells ring",
            'Three bells ring at noon: "exactly three small bells ring".',
        ),
        (
            "What grows in the glass garden?",
            "The glass garden grows silver beans in narrow pots.",
            "grows silver beans",
            'It grows silver beans: "grows silver beans".',
        ),
        (
            "Where is the paper boat kept?",
            "The paper boat is kept under the wooden bench.",
            "kept under the wooden bench",
            'The boat is under the bench: "kept under the wooden bench".',
        ),
        (
            "What is the robot's name?",
            "The tiny helper robot is named Pipkin.",
            "robot is named Pipkin",
            'The helper robot is Pipkin: "robot is named Pipkin".',
        ),
        (
            "When does the lantern turn on?",
            "The lantern turns on at 19:40 in the imaginary harbor.",
            "turns on at 19:40",
            'It turns on at 19:40: "turns on at 19:40".',
        ),
        (
            "What snack is served on the train?",
            "The paper train serves cinnamon stars as its evening snack.",
            "serves cinnamon stars",
            'The train serves cinnamon stars: "serves cinnamon stars".',
        ),
        (
            "How long is the library bridge?",
            "The library bridge is twelve wooden steps long.",
            "twelve wooden steps long",
            'It is twelve steps long: "twelve wooden steps long".',
        ),
    ],
    ids=[f"synthetic-question-{index}" for index in range(1, 11)],
)
def test_ten_synthetic_answers_quote_supporting_context(
    question, source_text, quote, answer
) -> None:
    result = make_result(source_text)
    response = make_response(answer, quote=quote)

    validated, sources = validate_rag_response(response, result)

    assert question
    assert quote in source_text
    assert quote in validated.content
    assert sources[0].quote == quote
