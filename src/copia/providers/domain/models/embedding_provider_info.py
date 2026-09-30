from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingProviderInfo:
    id: str
    display_name: str
    default_model: str
