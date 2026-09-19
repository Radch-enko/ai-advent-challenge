from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from ..domain.models.invariant import Invariant

MAX_INVARIANTS = 32


class InvariantsRepository:
    """Stores global Copia invariants separately from conversation transcripts."""

    def __init__(self, path: Path, legacy_sessions_root: Path | None = None) -> None:
        self._path = path.expanduser()
        self._legacy_sessions_root = (
            legacy_sessions_root.expanduser() if legacy_sessions_root is not None else None
        )
        self._lock = RLock()

    def load(self) -> list[Invariant]:
        with self._lock:
            if self._path.is_file():
                return self._read_items(self._path)
            migrated = self._load_legacy_items()
            if migrated:
                self._atomic_write(self._path, self._serialize(migrated))
            return migrated

    def save(self, items: list[Invariant]) -> None:
        if len(items) > MAX_INVARIANTS:
            raise ValueError("Invariant limit reached")
        with self._lock:
            self._atomic_write(self._path, self._serialize(items))

    def create(self, item: Invariant) -> Invariant:
        with self._lock:
            items = self.load()
            if len(items) >= MAX_INVARIANTS:
                raise ValueError("Invariant limit reached")
            self._atomic_write(self._path, self._serialize([*items, item]))
        return item

    def update(self, item_id: str, changes: dict[str, object]) -> Invariant:
        with self._lock:
            items = self.load()
            for index, item in enumerate(items):
                if item.id == item_id:
                    updated = item.model_copy(update=changes)
                    items[index] = updated
                    self._atomic_write(self._path, self._serialize(items))
                    return updated
        raise KeyError(item_id)

    def delete_item(self, item_id: str) -> None:
        with self._lock:
            items = self.load()
            retained = [item for item in items if item.id != item_id]
            if len(retained) == len(items):
                raise KeyError(item_id)
            self._atomic_write(self._path, self._serialize(retained))

    def delete(self) -> None:
        with self._lock:
            self._path.unlink(missing_ok=True)

    @staticmethod
    def _serialize(items: list[Invariant]) -> dict[str, object]:
        return {"items": [item.model_dump(mode="json") for item in items]}

    @classmethod
    def _read_items(cls, path: Path) -> list[Invariant]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("Invalid invariants file")
        return [cls._parse_item(item) for item in data["items"]]

    def _load_legacy_items(self) -> list[Invariant]:
        if self._legacy_sessions_root is None or not self._legacy_sessions_root.is_dir():
            return []
        items: list[Invariant] = []
        seen_ids: set[str] = set()
        for path in sorted(self._legacy_sessions_root.glob("*/invariants.json")):
            try:
                candidates = self._read_items(path)
            except (OSError, ValueError):
                continue
            for item in candidates:
                if item.id not in seen_ids and len(items) < MAX_INVARIANTS:
                    items.append(item)
                    seen_ids.add(item.id)
        return items

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".invariants-",
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
    def _parse_item(item: object) -> Invariant:
        if isinstance(item, dict) and "name" not in item and isinstance(item.get("category"), str):
            item = {
                **{key: value for key, value in item.items() if key != "category"},
                "name": item["category"].replace("_", " ").title(),
            }
        return Invariant.model_validate(item)
