from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ProviderTrace(BaseModel):
    status_code: int
    request_body: dict[str, Any]
    response_body: dict[str, Any]
