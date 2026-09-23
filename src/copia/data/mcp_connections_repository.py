from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ..domain.models.mcp import McpConnection


class McpConnectionsStorageError(RuntimeError):
    pass


class McpConnectionConflictError(RuntimeError):
    pass


class McpConnectionsRepository:
    def __init__(self, path: Path | None = None) -> None:
        self._path = (path or Path("~/.copia/mcp_connections.json")).expanduser()
        self._lock = threading.RLock()

    def list(self) -> list[McpConnection]:
        with self._lock:
            return sorted(self._load(), key=lambda item: (item.name.casefold(), item.id))

    def get(self, connection_id: str) -> McpConnection | None:
        return next((item for item in self.list() if item.id == connection_id), None)

    def save(self, connection: McpConnection) -> McpConnection:
        with self._lock:
            connections = self._load()
            existing = next(
                (index for index, item in enumerate(connections) if item.id == connection.id), None
            )
            if existing is None:
                connections.append(connection)
            else:
                connections[existing] = connection
            self._save(connections)
            return connection

    def create(self, connection: McpConnection) -> McpConnection:
        with self._lock:
            connections = self._load()
            if any(item.id == connection.id for item in connections):
                raise McpConnectionConflictError("MCP connection already exists")
            connections.append(connection)
            self._save(connections)
            return connection

    def delete(self, connection_id: str) -> bool:
        with self._lock:
            connections = self._load()
            remaining = [item for item in connections if item.id != connection_id]
            if len(remaining) == len(connections):
                return False
            self._save(remaining)
            return True

    def _load(self) -> list[McpConnection]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return TypeAdapter(list[McpConnection]).validate_python(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise McpConnectionsStorageError("MCP connections are unavailable") from error

    def _save(self, connections: list[McpConnection]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    [item.model_dump(mode="json") for item in connections],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            temporary.replace(self._path)
        except OSError as error:
            raise McpConnectionsStorageError("Could not save MCP connections") from error
