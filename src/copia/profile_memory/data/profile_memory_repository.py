from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from copia.profile_memory.data.profile_memory_limit_exceeded import ProfileMemoryLimitExceeded
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.storage.domain.services.path_identifiers import validate_path_identifier

MAX_PROFILE_MEMORY_ITEMS = 100


class ProfileMemoryRepository:
    """Atomically stores user-managed long-term memory outside profile and session JSON."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()
        self._lock = RLock()

    def load(self, profile_name: str) -> list[LongTermMemoryItem]:
        with self._lock:
            return self._load(profile_name)

    def _load(self, profile_name: str) -> list[LongTermMemoryItem]:
        path = self._path(profile_name)
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("Invalid profile memory file")
        return [LongTermMemoryItem.model_validate(item) for item in data["items"]]

    def save(self, profile_name: str, items: list[LongTermMemoryItem]) -> None:
        with self._lock:
            self._save(profile_name, items)

    def _save(self, profile_name: str, items: list[LongTermMemoryItem]) -> None:
        if len(items) > MAX_PROFILE_MEMORY_ITEMS:
            raise ProfileMemoryLimitExceeded
        path = self._path(profile_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": [item.model_dump(mode="json") for item in items]}
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".memory-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def create(self, profile_name: str, item: LongTermMemoryItem) -> LongTermMemoryItem:
        with self._lock:
            items = self._load(profile_name)
            if len(items) >= MAX_PROFILE_MEMORY_ITEMS:
                raise ProfileMemoryLimitExceeded
            self._save(profile_name, [*items, item])
        return item

    def update(
        self, profile_name: str, item_id: str, changes: dict[str, object]
    ) -> LongTermMemoryItem:
        with self._lock:
            items = self._load(profile_name)
            for index, item in enumerate(items):
                if item.id == item_id:
                    updated = item.model_copy(update=changes)
                    items[index] = updated
                    self._save(profile_name, items)
                    return updated
        raise KeyError(item_id)

    def delete_item(self, profile_name: str, item_id: str) -> None:
        with self._lock:
            items = self._load(profile_name)
            retained = [item for item in items if item.id != item_id]
            if len(retained) == len(items):
                raise KeyError(item_id)
            self._save(profile_name, retained)

    @staticmethod
    def _safe_name(profile_name: str) -> str:
        validate_path_identifier(profile_name, "profile name")
        return hashlib.sha256(profile_name.encode("utf-8")).hexdigest()

    def _path(self, profile_name: str) -> Path:
        return self._root / f"{self._safe_name(profile_name)}.json"
