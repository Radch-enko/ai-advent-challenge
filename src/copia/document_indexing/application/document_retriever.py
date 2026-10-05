from __future__ import annotations

import heapq
import json
import math
from typing import Any

from copia.common.domain.models.rag_settings import RagSettings
from copia.common.domain.services.llm_context_builder import LLMContextBuilder
from copia.common.domain.services.prompt_resources import render_prompt
from copia.document_indexing.data.index_artifact_store import IndexArtifactStore
from copia.document_indexing.domain.errors import DocumentRetrievalError
from copia.document_indexing.domain.models.rag_retrieval_result import RagRetrievalResult
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk
from copia.providers.application.embedding_router import EmbeddingRouter
from copia.providers.application.llm_router import LLMRouter
from copia.providers.domain.errors import ProviderError
from copia.providers.domain.models.generation_config import GenerationConfig
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.structured_output_config import StructuredOutputConfig
from copia.sessions.domain.models.chat_message import ChatMessage


class DocumentRetriever:
    def __init__(
        self,
        artifact_store: IndexArtifactStore,
        embedding_providers: EmbeddingRouter,
        llm_router: LLMRouter | None = None,
    ) -> None:
        self._artifacts = artifact_store
        self._embedding_providers = embedding_providers
        self._llm_router = llm_router

    def retrieve(
        self,
        question: str,
        settings: RagSettings | None = None,
        *,
        config: LLMConfig | None = None,
        history: list[ChatMessage] | None = None,
        summary: str = "",
        task_memory: list[dict[str, str]] | None = None,
    ) -> RetrievedChunk | RagRetrievalResult:
        """Keep the original single-best-chunk API for existing internal callers."""
        if settings is not None:
            return self.retrieve_with_settings(
                question,
                settings,
                config=config,
                history=history,
                summary=summary,
                task_memory=task_memory,
            )
        result = self.retrieve_with_settings(
            question,
            RagSettings(
                top_k_before=100,
                similarity_threshold=-1,
                top_k_after=100,
                query_rewrite_enabled=False,
            ),
        )
        if not result.context_chunks:
            raise DocumentRetrievalError(
                "RAG is enabled, but no document chunks passed the similarity threshold."
            )
        return result.context_chunks[0]

    def retrieve_with_settings(
        self,
        question: str,
        settings: RagSettings,
        *,
        config: LLMConfig | None = None,
        history: list[ChatMessage] | None = None,
        summary: str = "",
        task_memory: list[dict[str, str]] | None = None,
    ) -> RagRetrievalResult:
        if not question.strip():
            raise DocumentRetrievalError("RAG search requires a non-empty question")

        try:
            search_query = question
            rewritten_query = None
            if settings.query_rewrite_enabled:
                rewritten_query = self._rewrite_query(
                    question, history or [], summary, task_memory or [], config
                )
                search_query = rewritten_query

            candidates = self._search(search_query, settings)
            filtered = _filter_candidates(candidates, settings)
            if not filtered and search_query != question:
                candidates = self._search(question, settings)
                filtered = _filter_candidates(candidates, settings)
            selected_ids = {chunk.source.chunk_id for _, chunk in filtered}

            if settings.reranker_enabled and filtered:
                winner_id = self._rerank(question, filtered, config)
                if winner_id not in selected_ids:
                    raise DocumentRetrievalError(
                        "RAG reranker selected a chunk outside the filtered candidates."
                    )
                context_chunks = [
                    chunk for _, chunk in filtered if chunk.source.chunk_id == winner_id
                ]
            else:
                context_chunks = [chunk for _, chunk in filtered]

            context_chunk_ids = {item.source.chunk_id for item in context_chunks}
            sources = [
                chunk.source.model_copy(
                    update={
                        "similarity_score": score,
                        "selected_for_context": chunk.source.chunk_id in context_chunk_ids,
                    }
                )
                for score, chunk in filtered
            ]
            return RagRetrievalResult(
                context_chunks=context_chunks,
                filtered_sources=sources,
                rewritten_query=rewritten_query,
            )
        except DocumentRetrievalError:
            raise
        except ProviderError as error:
            raise DocumentRetrievalError(
                "RAG search failed. Check the embedding and language model provider configuration and retry."
            ) from error
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError) as error:
            raise DocumentRetrievalError(
                "RAG search failed because the local document index is unavailable or invalid."
            ) from error
        except Exception as error:
            raise DocumentRetrievalError(
                "RAG search failed. Check the provider configuration and document index, then retry."
            ) from error

    def contextualize(
        self,
        messages: list[ChatMessage],
        result: RagRetrievalResult | RetrievedChunk,
        *,
        allow_uncited_fallback: bool = False,
    ) -> list[ChatMessage]:
        chunks = result.context_chunks if isinstance(result, RagRetrievalResult) else [result]
        serialized_chunks = json.dumps(
            [
                {
                    "chunk_id": chunk.source.chunk_id,
                    "source": chunk.source.source,
                    "title": chunk.source.title,
                    "section": chunk.source.section,
                    "text": chunk.text,
                }
                for chunk in chunks
            ],
            ensure_ascii=False,
        )
        prompt_name = "rag_chat_context.md" if allow_uncited_fallback else "rag_context.md"
        context = render_prompt(
            "copia.document_indexing",
            prompt_name,
            retrieved_chunks_json=serialized_chunks,
        )
        return LLMContextBuilder.with_additional_system_context(messages, context)

    def _rewrite_query(
        self,
        question: str,
        history: list[ChatMessage],
        summary: str,
        task_memory: list[dict[str, str]],
        config: LLMConfig | None,
    ) -> str:
        router = self._required_llm_router(config)
        history_data = [
            {"role": message.role, "content": message.content}
            for message in history[-10:]
            if message.role in {"user", "assistant"}
        ]
        prompt = render_prompt(
            "copia.document_indexing",
            "query_rewrite.md",
            summary_json=json.dumps(summary, ensure_ascii=False),
            history_json=json.dumps(history_data, ensure_ascii=False),
            task_memory_json=json.dumps(task_memory, ensure_ascii=False),
            question_json=json.dumps(question, ensure_ascii=False),
        )
        response = router.complete(
            [ChatMessage(role="user", content=prompt)], _helper_config(config)
        )
        rewritten = response.content.strip()
        if not rewritten:
            raise DocumentRetrievalError("RAG query rewriting returned an empty search query.")
        return rewritten[:2000]

    def _rerank(
        self,
        question: str,
        candidates: list[tuple[float, RetrievedChunk]],
        config: LLMConfig | None,
    ) -> str:
        router = self._required_llm_router(config)
        candidate_data = [
            {
                "chunk_id": chunk.source.chunk_id,
                "title": chunk.source.title,
                "section": chunk.source.section,
                "text": chunk.text,
            }
            for _, chunk in candidates
        ]
        candidate_ids = [item["chunk_id"] for item in candidate_data]
        prompt = render_prompt(
            "copia.document_indexing",
            "rag_rerank.md",
            question_json=json.dumps(question, ensure_ascii=False),
            candidates_json=json.dumps(candidate_data, ensure_ascii=False),
        )
        helper_config = _helper_config(config).model_copy(
            update={
                "structured_output": StructuredOutputConfig(
                    schema={
                        "type": "object",
                        "properties": {
                            "selected_chunk_id": {
                                "type": "string",
                                "enum": candidate_ids,
                            }
                        },
                        "required": ["selected_chunk_id"],
                        "additionalProperties": False,
                    },
                    strict=True,
                )
            }
        )
        response = router.complete([ChatMessage(role="user", content=prompt)], helper_config)
        data = response.structured_data
        selected_id = data.get("selected_chunk_id") if isinstance(data, dict) else None
        if not isinstance(selected_id, str) or selected_id not in candidate_ids:
            raise DocumentRetrievalError("RAG reranker returned an invalid chunk selection.")
        return selected_id

    def _required_llm_router(self, config: LLMConfig | None) -> LLMRouter:
        if self._llm_router is None or config is None:
            raise DocumentRetrievalError(
                "RAG query rewriting and reranking require a configured conversation model."
            )
        return self._llm_router

    def _search(self, question: str, settings: RagSettings) -> list[tuple[float, RetrievedChunk]]:
        latest = self._artifacts.latest()
        if latest is None:
            raise DocumentRetrievalError(
                "RAG is enabled, but no completed document index is available."
            )

        manifest, run_path = latest
        provider_id = _required_string(manifest, "provider")
        model = _required_string(manifest, "model")
        dimension = manifest.get("embedding_dimension")
        if not isinstance(dimension, int) or dimension <= 0:
            raise ValueError("Invalid embedding dimension")

        provider = self._embedding_providers.provider(provider_id)
        if not provider.is_configured:
            raise ProviderError("Embedding provider is not configured")
        query_vectors = provider.embed([question], model)
        if len(query_vectors) != 1:
            raise ValueError("Embedding provider returned the wrong vector count")
        query_vector = _validated_vector(query_vectors[0], dimension)
        query_norm = math.sqrt(math.fsum(value * value for value in query_vector))
        if query_norm == 0:
            raise ValueError("Embedding provider returned a zero vector")

        index_path = run_path / "structure-aware.jsonl"
        scored: list[tuple[float, int, RetrievedChunk]] = []
        sequence = 0
        with index_path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                record = json.loads(line)
                chunk = _parse_chunk(record)
                vector = _validated_vector(record.get("embedding"), dimension)
                vector_norm = math.sqrt(math.fsum(value * value for value in vector))
                if vector_norm == 0:
                    raise ValueError("Index contains a zero vector")
                score = math.fsum(
                    left * right for left, right in zip(query_vector, vector, strict=True)
                ) / (query_norm * vector_norm)
                score = max(-1.0, min(1.0, score))
                item = (score, -sequence, chunk)
                if len(scored) < settings.top_k_before:
                    heapq.heappush(scored, item)
                elif item[:2] > scored[0][:2]:
                    heapq.heapreplace(scored, item)
                sequence += 1

        if not scored:
            raise DocumentRetrievalError(
                "RAG is enabled, but the document index contains no chunks."
            )
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [(score, chunk) for score, _, chunk in scored]


def _filter_candidates(
    candidates: list[tuple[float, RetrievedChunk]], settings: RagSettings
) -> list[tuple[float, RetrievedChunk]]:
    return [item for item in candidates if item[0] >= settings.similarity_threshold][
        : settings.top_k_after
    ]


def _helper_config(config: LLMConfig | None) -> LLMConfig:
    assert config is not None
    return LLMConfig(
        provider=config.provider,
        model=config.model,
        generation=GenerationConfig(max_output_tokens=128, temperature=0),
    )


def _required_string(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid {field}")
    return value


def _validated_vector(value: Any, expected_dimension: int) -> list[float]:
    if not isinstance(value, list) or len(value) != expected_dimension:
        raise ValueError("Invalid embedding vector dimension")
    if any(not isinstance(item, (int, float)) or not math.isfinite(item) for item in value):
        raise ValueError("Invalid embedding vector")
    return [float(item) for item in value]


def _parse_chunk(record: Any) -> RetrievedChunk:
    if not isinstance(record, dict):
        raise ValueError("Invalid index record")
    text = _required_string(record, "text")
    source = _required_string(record, "source")
    title = _required_string(record, "title")
    section = record.get("section", "")
    chunk_id = _required_string(record, "chunk_id")
    if not isinstance(section, str):
        raise ValueError("Invalid section")
    return RetrievedChunk(
        text=text,
        source={"chunk_id": chunk_id, "source": source, "title": title, "section": section},
    )
