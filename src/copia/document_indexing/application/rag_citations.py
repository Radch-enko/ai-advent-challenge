from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from copy import deepcopy
from typing import Any

from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.common.domain.services.llm_context_builder import LLMContextBuilder
from copia.document_indexing.domain.models.rag_retrieval_result import RagRetrievalResult
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.structured_output_config import StructuredOutputConfig
from copia.sessions.domain.models.chat_message import ChatMessage


class RagCitationValidationError(RuntimeError):
    """Raised when an LLM answer cannot be tied to exact retrieved evidence."""


RAG_CITATION_WARNING = "⚠️ Цитаты не прошли проверку. Ответ модели может быть ошибочным."


def strip_rag_citation_warning(text: str) -> str:
    if text.startswith(RAG_CITATION_WARNING):
        return text[len(RAG_CITATION_WARNING) :].lstrip()
    return text


def rag_answer_schema(
    base_schema: dict[str, Any] | None = None,
    *,
    allow_uncited_fallback: bool = False,
) -> dict[str, Any]:
    schema = (
        deepcopy(base_schema)
        if base_schema is not None
        else {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
    )
    properties = schema.setdefault("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("RAG structured output schema must define object properties")
    properties.pop("answer_mode", None)
    properties["answer"] = {"type": "string", "minLength": 1}
    properties["citations"] = {
        "type": "array",
        "minItems": 0 if allow_uncited_fallback else 1,
        "items": {
            "type": "object",
            "properties": {
                "chunk_id": {"type": "string", "minLength": 1},
                "quote": {"type": "string", "minLength": 1},
            },
            "required": ["chunk_id", "quote"],
            "additionalProperties": False,
        },
    }
    required = schema.setdefault("required", [])
    if not isinstance(required, list):
        raise ValueError("RAG structured output schema must define required properties")
    required_fields = [field for field in required if field != "answer_mode"]
    schema["required"] = list(dict.fromkeys([*required_fields, "answer", "citations"]))
    schema["additionalProperties"] = False
    return schema


def complete_with_citation_recovery(
    complete: Callable[[Sequence[ChatMessage], LLMConfig], LLMResponse],
    messages: list[ChatMessage],
    config: LLMConfig,
    result: RagRetrievalResult,
    *,
    retry_complete: Callable[[Sequence[ChatMessage], LLMConfig], LLMResponse] | None = None,
    allow_uncited_fallback: bool = False,
) -> tuple[LLMResponse, list[KnowledgeSource]]:
    fallback_allowed = allow_uncited_fallback and not result.context_chunks
    structured_config = config.model_copy(
        update={
            "structured_output": StructuredOutputConfig(
                schema=rag_answer_schema(
                    config.structured_output.json_schema if config.structured_output else None,
                    allow_uncited_fallback=fallback_allowed,
                ),
                strict=True,
            )
        }
    )
    previous_response = None
    for attempt in range(2):
        request_messages = messages
        if attempt:
            request_messages = [
                *messages,
                *(
                    [ChatMessage(role="assistant", content=previous_response.content)]
                    if previous_response is not None
                    else []
                ),
                ChatMessage(
                    role="user",
                    content=(_citation_retry_instruction(fallback_allowed)),
                ),
            ]
        response = (
            (retry_complete or complete)(request_messages, structured_config)
            if attempt
            else complete(request_messages, structured_config)
        )
        previous_response = response
        try:
            return validate_rag_response(response, result, allow_uncited_fallback=fallback_allowed)
        except RagCitationValidationError:
            if attempt:
                return _unverified_response(response, result)
    raise AssertionError("Citation retry loop terminated unexpectedly")


def validate_rag_response(
    response: LLMResponse,
    result: RagRetrievalResult,
    *,
    allow_uncited_fallback: bool = False,
) -> tuple[LLMResponse, list[KnowledgeSource]]:
    data = response.structured_data
    if not isinstance(data, dict):
        raise RagCitationValidationError("RAG answer failed citation validation after retry.")

    answer = data.get("answer")
    citations = data.get("citations")
    if not isinstance(answer, str) or not answer.strip() or not isinstance(citations, list):
        raise RagCitationValidationError("RAG answer failed citation validation after retry.")
    if not citations:
        if allow_uncited_fallback and not result.context_chunks:
            return response.model_copy(update={"content": answer.strip()}), []
        raise RagCitationValidationError("RAG answer failed citation validation after retry.")

    chunks_by_id = {chunk.source.chunk_id: chunk for chunk in result.context_chunks}
    metadata_by_id = {source.chunk_id: source for source in result.filtered_sources}
    verified_sources: list[KnowledgeSource] = []
    for citation in citations:
        if not isinstance(citation, dict):
            raise RagCitationValidationError("RAG answer failed citation validation after retry.")
        chunk_id = citation.get("chunk_id")
        quote = citation.get("quote")
        chunk = chunks_by_id.get(chunk_id) if isinstance(chunk_id, str) else None
        if (
            chunk is None
            or not isinstance(quote, str)
            or not quote.strip()
            or quote not in chunk.text
            or quote not in answer
        ):
            raise RagCitationValidationError("RAG answer failed citation validation after retry.")
        source = metadata_by_id.get(chunk_id, chunk.source)
        verified_sources.append(source.model_copy(update={"quote": quote}))

    return response.model_copy(update={"content": answer}), verified_sources


def complete_with_no_evidence_fallback(
    complete: Callable[[Sequence[ChatMessage], LLMConfig], LLMResponse],
    messages: list[ChatMessage],
    config: LLMConfig,
    system_context: str,
) -> LLMResponse:
    contextualized = LLMContextBuilder.with_additional_system_context(messages, system_context)
    fallback_config = config.model_copy(
        update={
            "structured_output": StructuredOutputConfig(
                schema=rag_answer_schema(allow_uncited_fallback=True), strict=True
            )
        }
    )
    response = complete(contextualized, fallback_config)
    try:
        validated, _ = validate_rag_response(
            response, RagRetrievalResult(), allow_uncited_fallback=True
        )
    except RagCitationValidationError:
        validated = response.model_copy(update={"content": _response_answer(response)})
    return validated.model_copy(update={"structured_data": None, "tool_calls": []})


def _citation_retry_instruction(allow_uncited_fallback: bool) -> str:
    if allow_uncited_fallback:
        return (
            "The previous response did not pass citation validation. Return a corrected structured "
            "response. If the excerpts support the answer, cite only exact quotes from provided "
            "chunks. If they do not support it, answer using the available conversation and "
            "general knowledge, explain in your own words that the knowledge base did not contain "
            "relevant information, and use no citations. Never invent a citation."
        )
    return (
        "The previous response did not pass citation validation. Return a corrected structured "
        "response. Every citation must use a provided chunk_id, its quote must exactly match that "
        "chunk, and the exact quote must appear in answer."
    )


def _unverified_response(
    response: LLMResponse, result: RagRetrievalResult
) -> tuple[LLMResponse, list[KnowledgeSource]]:
    answer = _response_answer(response)
    sources = _sources_with_exact_quotes(response, result)
    content = f"{RAG_CITATION_WARNING}\n\n{answer}"
    return response.model_copy(update={"content": content}), sources


def _response_answer(response: LLMResponse) -> str:
    data = response.structured_data
    answer = data.get("answer") if isinstance(data, dict) else None
    if isinstance(answer, str) and answer.strip():
        return answer.strip()

    try:
        decoded = json.loads(response.content)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, dict):
        answer = decoded.get("answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()

    content = response.content.strip()
    if content and not content.startswith(("{", "[")):
        return content
    return "Не удалось получить читаемый ответ от модели."


def _sources_with_exact_quotes(
    response: LLMResponse, result: RagRetrievalResult
) -> list[KnowledgeSource]:
    data = response.structured_data
    if not isinstance(data, dict):
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    citations = data.get("citations")
    if not isinstance(citations, list):
        return []

    chunks_by_id = {chunk.source.chunk_id: chunk for chunk in result.context_chunks}
    sources_by_id = {source.chunk_id: source for source in result.filtered_sources}
    verified_sources: list[KnowledgeSource] = []
    seen_citations: set[tuple[str, str]] = set()
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        chunk_id = citation.get("chunk_id")
        quote = citation.get("quote")
        if not isinstance(chunk_id, str) or not isinstance(quote, str) or not quote.strip():
            continue
        chunk = chunks_by_id.get(chunk_id)
        citation_key = (chunk_id, quote)
        if chunk is None or quote not in chunk.text or citation_key in seen_citations:
            continue
        source = sources_by_id.get(chunk_id, chunk.source)
        verified_sources.append(source.model_copy(update={"quote": quote}))
        seen_citations.add(citation_key)
    return verified_sources
