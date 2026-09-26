from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.storage.domain.services.path_identifiers import validate_path_identifier


class WorkingMemoryRepository:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()
        self._lock = RLock()

    def load(self, session_id: str) -> list[WorkingMemoryItem]:
        with self._lock:
            path = self._path(session_id)
            if not path.is_file():
                return []
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ValueError("Invalid working memory file")
            return [WorkingMemoryItem.model_validate(item) for item in data["items"]]

    def save(self, session_id: str, items: list[WorkingMemoryItem]) -> None:
        with self._lock:
            self._write(session_id, items)
            self._undo_path(session_id).unlink(missing_ok=True)

    def save_preserving_undo(self, session_id: str, items: list[WorkingMemoryItem]) -> None:
        with self._lock:
            self._write(session_id, items)

    def save_automatic(
        self,
        session_id: str,
        before: list[WorkingMemoryItem],
        after: list[WorkingMemoryItem],
    ) -> None:
        with self._lock:
            main_path = self._path(session_id)
            undo_path = self._undo_path(session_id)
            previous_main = main_path.read_bytes() if main_path.is_file() else None
            previous_undo = undo_path.read_bytes() if undo_path.is_file() else None
            try:
                self._write(session_id, after)
                self._atomic_write(
                    undo_path,
                    {"items": [item.model_dump(mode="json") for item in before]},
                )
            except Exception:
                self._restore_file(main_path, previous_main)
                self._restore_file(undo_path, previous_undo)
                raise

    def undo_last(self, session_id: str) -> list[WorkingMemoryItem] | None:
        with self._lock:
            path = self._undo_path(session_id)
            if not path.is_file():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            items = [WorkingMemoryItem.model_validate(item) for item in data.get("items", [])]
            self._write(session_id, items)
            path.unlink(missing_ok=True)
            return items

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._path(session_id).unlink(missing_ok=True)
            self._undo_path(session_id).unlink(missing_ok=True)

    def _write(self, session_id: str, items: list[WorkingMemoryItem]) -> None:
        self._atomic_write(
            self._path(session_id),
            {"items": [item.model_dump(mode="json") for item in items]},
        )

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".working-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(data, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _restore_file(path: Path, content: bytes | None) -> None:
        if content is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=".working-", suffix=".tmp", delete=False
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _path(self, session_id: str) -> Path:
        validate_path_identifier(session_id, "session ID")
        return self._root / session_id / "working_memory.json"

    def _undo_path(self, session_id: str) -> Path:
        validate_path_identifier(session_id, "session ID")
        return self._root / session_id / "working_memory.undo.json"
