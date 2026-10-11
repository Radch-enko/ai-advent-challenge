from __future__ import annotations

from typing import Any

import httpx

from copia.common.configuration import get_settings
from copia.providers.data.http_logging import record_response, record_stream_response
from copia.providers.domain.errors import ProviderError
from copia.providers.domain.models.embedding_provider_info import EmbeddingProviderInfo


class OllamaEmbeddingProvider:
    info = EmbeddingProviderInfo(
        id="ollama",
        display_name="Ollama",
        default_model="qwen3-embedding:0.6b",
    )

    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        configured_url = str(get_settings().ollama_base_url) if base_url is None else base_url
        origin = (base_url or configured_url).rstrip("/")
        self._configured = (
            base_url is not None or configured_url.rstrip("/") != "https://ollama.example.invalid"
        )
        self._models_url = f"{origin}/v1/models"
        self._embeddings_url = f"{origin}/v1/embeddings"
        self._client = client or httpx.Client(timeout=120.0)

    @property
    def is_configured(self) -> bool:
        return self._configured

    def list_models(self) -> list[str]:
        response: httpx.Response | None = None
        try:
            response = self._client.get(self._models_url)
            response.raise_for_status()
            data = response.json().get("data", [])
            return sorted(
                item["id"]
                for item in data
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError("Ollama embedding model request failed") from error
        finally:
            if response is not None:
                record_response(response)

    def count_tokens(self, text: str, model: str) -> int:
        # Оценка по символам позволяет разбивать текст без сетевой загрузки tokenizer.
        return len(text)

    def split_text(self, text: str, model: str, max_tokens: int, overlap_tokens: int) -> list[str]:
        if max_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("Token window settings are invalid")
        if not text:
            return []
        step = max_tokens - overlap_tokens
        chunks: list[str] = []
        for start in range(0, len(text), step):
            end = min(start + max_tokens, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
        return chunks

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        if not texts:
            return []
        response: httpx.Response | None = None
        try:
            response = self._client.post(
                self._embeddings_url,
                json={"model": model, "input": texts},
            )
            response.raise_for_status()
            data: Any = response.json()["data"]
            indexed_vectors = sorted(
                (
                    (item["index"], item["embedding"])
                    for item in data
                    if isinstance(item, dict)
                    and isinstance(item.get("index"), int)
                    and isinstance(item.get("embedding"), list)
                ),
                key=lambda item: item[0],
            )
            vectors = [[float(value) for value in vector] for _, vector in indexed_vectors]
            if len(vectors) != len(texts):
                raise ProviderError("Ollama returned an incomplete embedding batch")
            return vectors
        except ProviderError:
            raise
        except httpx.HTTPStatusError as error:
            raise ProviderError(
                f"Ollama embedding request failed with status {error.response.status_code}",
                status_code=error.response.status_code,
            ) from error
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError("Ollama embedding request failed") from error
        finally:
            if response is not None:
                record_stream_response(response)

    def close(self) -> None:
        self._client.close()
