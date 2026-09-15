from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from ..domain.models.config import ChatMessage
from ..domain.models.session import BranchTranscript, ChatSession, ChatSessionSummary


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
            summaries.append(
                ChatSessionSummary(
                    id=session.id,
                    title=session.title,
                    profile_name=session.profile_name,
                    updated_at=session.updated_at,
                )
            )
        return sorted(summaries, key=lambda session: session.updated_at, reverse=True)

    def load(self, session_id: str) -> ChatSession | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        session = ChatSession.model_validate_json(path.read_text(encoding="utf-8"))
        if session.branching is not None:
            session.messages = self.load_branch(session.id, session.branching.active_branch_id)
        return session

    def save(self, session: ChatSession) -> None:
        path = self._path(session.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        stored_session = session
        if session.branching is not None:
            self.save_branch(session.id, session.branching.active_branch_id, session.messages)
            stored_session = session.model_copy(deep=True)
            stored_session.messages = []
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".session-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(stored_session.model_dump_json(indent=2))
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)

    def delete(self, session_id: str) -> bool:
        directory = self._path(session_id).parent
        if not directory.is_dir():
            return False
        shutil.rmtree(directory)
        return True

    def load_facts(self, session_id: str) -> dict[str, str]:
        path = self._facts_path(session_id)
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in data.items()
        ):
            raise ValueError("Invalid facts file")
        return data

    def save_facts(self, session_id: str, facts: dict[str, str]) -> None:
        path = self._facts_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".facts-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(facts, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)

    def load_branch(self, session_id: str, branch_id: str) -> list[ChatMessage]:
        path = self._branch_path(session_id, branch_id)
        if not path.is_file():
            raise ValueError(f"Unknown branch: {branch_id}")
        transcript = BranchTranscript.model_validate_json(path.read_text(encoding="utf-8"))
        return list(transcript.messages)

    def save_branch(self, session_id: str, branch_id: str, messages: list[ChatMessage]) -> None:
        path = self._branch_path(session_id, branch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        transcript = BranchTranscript(messages=messages)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".branch-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(transcript.model_dump_json(indent=2))
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)

    def _path(self, session_id: str) -> Path:
        if Path(session_id).name != session_id:
            raise ValueError("Invalid session ID")
        return self._root / session_id / "session.json"

    def _facts_path(self, session_id: str) -> Path:
        if Path(session_id).name != session_id:
            raise ValueError("Invalid session ID")
        return self._root / session_id / "facts.json"

    def _branch_path(self, session_id: str, branch_id: str) -> Path:
        if Path(session_id).name != session_id or Path(branch_id).name != branch_id:
            raise ValueError("Invalid session or branch ID")
        return self._root / session_id / "branches" / f"{branch_id}.json"
