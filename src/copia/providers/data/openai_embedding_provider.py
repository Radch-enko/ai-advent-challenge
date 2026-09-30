from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx
import tiktoken

from copia.common.configuration import get_settings
from copia.providers.data.http_logging import record_response, record_stream_response
from copia.providers.domain.errors import ProviderError
from copia.providers.domain.models.embedding_provider_info import EmbeddingProviderInfo


@lru_cache(maxsize=16)
def _encoding_for_model(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


class OpenAIEmbeddingProvider:
    MODELS_URL = "https://api.openai.com/v1/models"
    EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
    info = EmbeddingProviderInfo(
        id="openai",
        display_name="OpenAI",
        default_model="text-embedding-3-small",
    )

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        configured_key = get_settings().openai_api_key
        self._api_key = api_key or (
            configured_key.get_secret_value() if configured_key is not None else None
        )
        self._client = client or httpx.Client(timeout=60.0)

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[str]:
        if not self._api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        response: httpx.Response | None = None
        try:
            response = self._client.get(
                self.MODELS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            return sorted(
                {
                    item["id"]
                    for item in data
                    if isinstance(item, dict)
                    and isinstance(item.get("id"), str)
                    and item["id"].startswith("text-embedding-")
                }
            )
        except httpx.HTTPStatusError as error:
            raise ProviderError(
                f"OpenAI embedding model request failed with status {error.response.status_code}",
                status_code=error.response.status_code,
            ) from error
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError("OpenAI embedding model request failed") from error
        finally:
            if response is not None:
                record_response(response)

    def count_tokens(self, text: str, model: str) -> int:
        return len(_encoding_for_model(model).encode(text, disallowed_special=()))

    def split_text(
        self,
        text: str,
        model: str,
        max_tokens: int,
        overlap_tokens: int,
    ) -> list[str]:
        if max_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("Token window settings are invalid")
        encoding = _encoding_for_model(model)
        token_ids = encoding.encode(text, disallowed_special=())
        if not token_ids:
            return []
        step = max_tokens - overlap_tokens
        chunks: list[str] = []
        start = 0
        while start < len(token_ids):
            end = min(start + max_tokens, len(token_ids))
            chunks.append(encoding.decode(token_ids[start:end]))
            if end == len(token_ids):
                break
            start += step
        return chunks

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        if not self._api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        if not texts:
            return []
        payload: dict[str, Any] = {"model": model, "input": texts}
        response: httpx.Response | None = None
        try:
            response = self._client.post(
                self.EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
            raw_data = response.json()["data"]
            indexed_vectors = [
                (item["index"], item["embedding"])
                for item in raw_data
                if isinstance(item, dict)
                and isinstance(item.get("index"), int)
                and isinstance(item.get("embedding"), list)
            ]
            indexed_vectors.sort(key=lambda item: item[0])
            vectors = [[float(value) for value in vector] for _, vector in indexed_vectors]
            if len(vectors) != len(texts):
                raise ProviderError("OpenAI returned an incomplete embedding batch")
            return vectors
        except ProviderError:
            raise
        except httpx.HTTPStatusError as error:
            raise ProviderError(
                f"OpenAI embedding request failed with status {error.response.status_code}",
                status_code=error.response.status_code,
                request_body={"model": model, "input_count": len(texts)},
            ) from error
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(
                "OpenAI embedding request failed",
                request_body={"model": model, "input_count": len(texts)},
            ) from error
        finally:
            if response is not None:
                # Запрос содержит полный текст чанков, поэтому логируем только HTTP-метаданные.
                record_stream_response(response)

    def close(self) -> None:
        self._client.close()
