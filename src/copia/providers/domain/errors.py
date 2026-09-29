from __future__ import annotations

from typing import Any


class ProviderError(RuntimeError):
    """An error returned while communicating with an LLM provider."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        request_body: dict[str, Any] | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_body = request_body or {}
        self.response_body = response_body if response_body is not None else {"error": message}
