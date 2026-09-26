from __future__ import annotations

from pydantic import BaseModel


class ProviderModel(BaseModel):
    id: str
    context_window: int | None = None
