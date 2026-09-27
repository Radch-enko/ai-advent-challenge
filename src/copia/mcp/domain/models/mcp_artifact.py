from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class McpArtifact:
    data: bytes
    mime_type: str
    filename: str


@dataclass(frozen=True)
class StoredMcpArtifact:
    artifact_id: str
    filename: str
    mime_type: str
