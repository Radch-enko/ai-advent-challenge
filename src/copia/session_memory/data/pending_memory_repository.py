from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.storage.domain.services.path_identifiers import validate_path_identifier


class PendingMemoryRepository:
    """Session-scoped durable storage for unapproved long-term suggestions."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()

    def load(self, session_id: str) -> list[PendingMemorySuggestion]:
        path = self._path(session_id)
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Invalid pending memory file")
        return [PendingMemorySuggestion.model_validate(item) for item in data]

    def save(self, session_id: str, suggestions: list[PendingMemorySuggestion]) -> None:
        path = self._path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".pending-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(
                    [item.model_dump(mode="json") for item in suggestions],
                    temporary,
                    ensure_ascii=False,
                    indent=2,
                )
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def delete(self, session_id: str) -> None:
        self._path(session_id).unlink(missing_ok=True)

    def _path(self, session_id: str) -> Path:
        validate_path_identifier(session_id, "session ID")
        return self._root / session_id / "pending_memory.json"
