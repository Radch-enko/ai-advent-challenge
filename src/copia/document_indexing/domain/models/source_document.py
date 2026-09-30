from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDocument:
    source: str
    title: str
    suffix: str
    text: str
    size_bytes: int
