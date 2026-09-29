from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class ConversationRepository:
    """Persists conversation metadata and replayable SSE events in SQLite."""

    TTL_SECONDS = 24 * 60 * 60
    MAX_CONVERSATIONS = 500
    MAX_CONVERSATION_BYTES = 1024 * 1024
    MAX_TOTAL_EVENT_BYTES = 128 * 1024 * 1024

    def __init__(self, path: Path | str) -> None:
        configured_path = str(path)
        self._path = (
            configured_path
            if configured_path == ":memory:"
            else str(Path(configured_path).expanduser())
        )
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self._path, timeout=5.0, check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys=ON")
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=64")
            connection.execute("PRAGMA journal_size_limit=0")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS conversation_events (
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    PRIMARY KEY (conversation_id, sequence)
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS conversation_expiry ON conversations(updated_at)"
            )
            connection.execute(f"PRAGMA max_page_count={self.MAX_TOTAL_EVENT_BYTES // 4096}")
            connection.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def load(self) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            self._prune(connection)
            rows = connection.execute(
                "SELECT id, request_id, fingerprint, status FROM conversations ORDER BY created_at"
            ).fetchall()
            result = []
            for conversation_id, request_id, fingerprint, status in rows:
                events = connection.execute(
                    "SELECT sequence, event_type, payload FROM conversation_events "
                    "WHERE conversation_id = ? ORDER BY sequence",
                    (conversation_id,),
                ).fetchall()
                result.append(
                    {
                        "id": conversation_id,
                        "request_id": request_id,
                        "fingerprint": fingerprint,
                        "status": status,
                        "events": [
                            {
                                "id": f"{conversation_id}:{sequence}",
                                "event": event_type,
                                "data": json.loads(payload),
                            }
                            for sequence, event_type, payload in events
                        ],
                    }
                )
            connection.commit()
            return result

    def create(self, conversation_id: str, request_id: str, fingerprint: str) -> bool:
        now = time.time()
        with self._lock, self._connection() as connection:
            self._prune(connection)
            existing = connection.execute(
                "SELECT id FROM conversations WHERE request_id = ?", (request_id,)
            ).fetchone()
            if existing:
                return False
            self._evict_to_count(connection, self.MAX_CONVERSATIONS - 1)
            count = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            if count >= self.MAX_CONVERSATIONS:
                raise ConversationStorageLimitError("Conversation storage is full")
            try:
                connection.execute(
                    "INSERT INTO conversations(id, request_id, fingerprint, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'running', ?, ?)",
                    (conversation_id, request_id, fingerprint, now, now),
                )
            except sqlite3.Error as error:
                raise ConversationStorageLimitError("Conversation storage is full") from error
            connection.commit()
            return True

    def append_event(self, conversation_id: str, sequence: int, event: dict[str, Any]) -> bool:
        payload = json.dumps(event["data"], ensure_ascii=False, separators=(",", ":"))
        size = len(payload.encode("utf-8")) + len(event["event"].encode("utf-8")) + 32
        terminal = event["event"] in {"conversation.completed", "conversation.failed"}
        try:
            with self._lock, self._connection() as connection:
                self._prune(connection)
                usage = connection.execute(
                    "SELECT COALESCE(SUM(size_bytes), 0) FROM conversation_events "
                    "WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()[0]
                total = connection.execute(
                    "SELECT COALESCE(SUM(size_bytes), 0) FROM conversation_events"
                ).fetchone()[0]
                if not terminal and (
                    usage + size > self.MAX_CONVERSATION_BYTES
                    or total + size > self.MAX_TOTAL_EVENT_BYTES
                ):
                    self._evict_completed(connection, needed=size, exclude=conversation_id)
                    total = connection.execute(
                        "SELECT COALESCE(SUM(size_bytes), 0) FROM conversation_events"
                    ).fetchone()[0]
                    if (
                        usage + size > self.MAX_CONVERSATION_BYTES
                        or total + size > self.MAX_TOTAL_EVENT_BYTES
                    ):
                        return False
                connection.execute(
                    "INSERT INTO conversation_events(conversation_id, sequence, event_type, payload, size_bytes) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (conversation_id, sequence, event["event"], payload, size),
                )
                status = "running"
                if event["event"] == "conversation.completed":
                    status = "completed"
                elif event["event"] == "conversation.failed":
                    status = "failed"
                connection.execute(
                    "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
                    (status, time.time(), conversation_id),
                )
                return True
        except sqlite3.Error:
            return False

    def get_by_id(self, conversation_id: str) -> str | None:
        with self._lock, self._connection() as connection:
            self._prune(connection)
            row = connection.execute(
                "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            connection.commit()
            return row[0] if row else None

    def conversation_ids(self) -> set[str]:
        with self._lock, self._connection() as connection:
            self._prune(connection)
            rows = connection.execute("SELECT id FROM conversations").fetchall()
            return {row[0] for row in rows}

    def get_by_request_id(self, request_id: str) -> str | None:
        with self._lock, self._connection() as connection:
            self._prune(connection)
            row = connection.execute(
                "SELECT id FROM conversations WHERE request_id = ?", (request_id,)
            ).fetchone()
            connection.commit()
            return row[0] if row else None

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._db
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    def _prune(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "DELETE FROM conversations WHERE updated_at < ?",
            (time.time() - self.TTL_SECONDS,),
        )
        self._evict_to_count(connection, self.MAX_CONVERSATIONS)

    @staticmethod
    def _evict_to_count(connection: sqlite3.Connection, count: int) -> None:
        current = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        excess = current - count
        if excess > 0:
            connection.execute(
                "DELETE FROM conversations WHERE id IN (SELECT id FROM conversations "
                "WHERE status != 'running' ORDER BY updated_at LIMIT ?)",
                (excess,),
            )

    @staticmethod
    def _evict_completed(connection: sqlite3.Connection, needed: int, exclude: str) -> None:
        total = connection.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) FROM conversation_events"
        ).fetchone()[0]
        while total + needed > ConversationRepository.MAX_TOTAL_EVENT_BYTES:
            row = connection.execute(
                "SELECT id FROM conversations WHERE status != 'running' AND id != ? "
                "ORDER BY updated_at LIMIT 1",
                (exclude,),
            ).fetchone()
            if row is None:
                return
            size = connection.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM conversation_events WHERE conversation_id = ?",
                (row[0],),
            ).fetchone()[0]
            connection.execute("DELETE FROM conversations WHERE id = ?", (row[0],))
            total -= size


class ConversationStorageLimitError(RuntimeError):
    pass
