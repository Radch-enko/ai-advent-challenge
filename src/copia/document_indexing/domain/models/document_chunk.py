from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    source: str
    title: str
    section: str
    chunk_id: str
    token_count: int
