from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from copia.document_indexing.data.atomic_json_write import atomic_json_write
from copia.document_indexing.domain.errors import DocumentIndexingError


class IndexArtifactStore:
    def __init__(self, index_root: Path) -> None:
        self._root = index_root
        self._runs = index_root / "runs"
        self._latest_path = index_root / "latest.json"

    @property
    def root(self) -> Path:
        return self._root

    def create_run(self, run_id: str) -> Path:
        if Path(run_id).name != run_id or run_id in {"", ".", ".."}:
            raise DocumentIndexingError("Invalid indexing run identifier")
        path = self._runs / run_id
        path.mkdir(parents=True, exist_ok=False)
        return path

    @staticmethod
    def temporary_jsonl_path(run_path: Path, strategy_id: str) -> Path:
        return run_path / f"{strategy_id}.jsonl.tmp"

    @staticmethod
    def commit_jsonl(run_path: Path, strategy_id: str) -> None:
        os.replace(
            run_path / f"{strategy_id}.jsonl.tmp",
            run_path / f"{strategy_id}.jsonl",
        )

    @staticmethod
    def write_json(run_path: Path, filename: str, value: Any) -> None:
        atomic_json_write(run_path / filename, value)

    @staticmethod
    def write_text(run_path: Path, filename: str, value: str) -> None:
        path = run_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def publish_latest(self, run_id: str) -> None:
        atomic_json_write(self._latest_path, {"run_id": run_id})

    def latest(self) -> tuple[dict[str, Any], Path] | None:
        if not self._latest_path.exists():
            return None
        try:
            pointer = json.loads(self._latest_path.read_text(encoding="utf-8"))
            run_id = pointer["run_id"]
            if not isinstance(run_id, str) or Path(run_id).name != run_id:
                raise ValueError("Invalid run id")
            run_path = self._runs / run_id
            manifest = json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))
            return manifest, run_path
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise DocumentIndexingError("The latest document index pointer is invalid") from error

    def remove_temporary_files(self, run_path: Path) -> None:
        (run_path / "structure-aware.jsonl.tmp").unlink(missing_ok=True)
