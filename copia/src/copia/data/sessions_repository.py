from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from ..domain.models.session import ChatSession, ChatSessionSummary


class SessionsRepository:
    """Stores each chat in its own JSON file outside the project directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()

    def list(self) -> list[ChatSessionSummary]:
        if not self._root.exists():
            return []
        summaries: list[ChatSessionSummary] = []
        for path in self._root.glob("*/session.json"):
            try:
                session = ChatSession.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            summaries.append(ChatSessionSummary(
                id=session.id,
                title=session.title,
                profile_name=session.profile_name,
                updated_at=session.updated_at,
            ))
        return sorted(summaries, key=lambda session: session.updated_at, reverse=True)

    def load(self, session_id: str) -> ChatSession | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        return ChatSession.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, session: ChatSession) -> None:
        path = self._path(session.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".session-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(session.model_dump_json(indent=2))
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)

    def delete(self, session_id: str) -> bool:
        directory = self._path(session_id).parent
        if not directory.is_dir():
            return False
        shutil.rmtree(directory)
        return True

    def _path(self, session_id: str) -> Path:
        if Path(session_id).name != session_id:
            raise ValueError("Invalid session ID")
        return self._root / session_id / "session.json"
