from __future__ import annotations

import json
import threading
from pathlib import Path

from copia.document_indexing.data.atomic_json_write import atomic_json_write
from copia.document_indexing.domain.errors import DocumentIndexingError
from copia.document_indexing.domain.models.embedding_settings import EmbeddingSettings


class EmbeddingSettingsRepository:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def load(self) -> EmbeddingSettings:
        with self._lock:
            if not self._path.exists():
                return EmbeddingSettings.defaults()
            try:
                value = json.loads(self._path.read_text(encoding="utf-8"))
                return EmbeddingSettings.model_validate(value)
            except (OSError, ValueError) as error:
                raise DocumentIndexingError(
                    "The persisted embedding settings are invalid"
                ) from error

    def save(self, settings: EmbeddingSettings) -> EmbeddingSettings:
        with self._lock:
            atomic_json_write(self._path, settings.model_dump(mode="json"))
        return settings
