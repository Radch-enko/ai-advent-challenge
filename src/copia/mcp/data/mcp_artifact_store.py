from __future__ import annotations

import uuid
from pathlib import Path

from copia.mcp.domain.models.mcp_artifact import McpArtifact, StoredMcpArtifact
from copia.storage.domain.services.path_identifiers import validate_path_identifier


class McpArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()

    def save(self, session_id: str, artifact: McpArtifact) -> StoredMcpArtifact:
        validate_path_identifier(session_id, "session ID")
        artifact_id = uuid.uuid4().hex
        session_root = self._root / session_id
        session_root.mkdir(parents=True, exist_ok=True)
        path = session_root / f"{artifact_id}.png"
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_bytes(artifact.data)
        temporary.replace(path)
        return StoredMcpArtifact(
            artifact_id=artifact_id,
            filename=artifact.filename,
            mime_type=artifact.mime_type,
        )

    def path(self, session_id: str, artifact_id: str) -> Path | None:
        try:
            validate_path_identifier(session_id, "session ID")
            validate_path_identifier(artifact_id, "artifact ID")
        except ValueError:
            return None
        path = self._root / session_id / f"{artifact_id}.png"
        return path if path.is_file() else None
