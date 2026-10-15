import json
import math
import os
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path

from code_assistance.errors import IndexCompatibilityError, IndexCorruptionError
from code_assistance.models import Chunk, SearchHit


class IndexStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                self.database_path.parent.chmod(0o700)
            self._initialize()
        except (OSError, sqlite3.DatabaseError) as exc:
            raise IndexCorruptionError(
                f"Cannot open local index at {self.database_path}. "
                "Check permissions or remove the damaged index."
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS documents (
                        path TEXT PRIMARY KEY,
                        digest TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS chunks (
                        path TEXT NOT NULL,
                        ordinal INTEGER NOT NULL,
                        start_line INTEGER NOT NULL,
                        end_line INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        vector_json TEXT NOT NULL,
                        PRIMARY KEY (path, ordinal),
                        FOREIGN KEY (path) REFERENCES documents(path) ON DELETE CASCADE
                    );
                    """
                )
        if os.name != "nt":
            self.database_path.chmod(0o600)

    def metadata(self) -> dict[str, str]:
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute("SELECT key, value FROM metadata").fetchall()
        except sqlite3.DatabaseError as exc:
            raise self._corruption_error(exc) from exc
        return {str(key): str(value) for key, value in rows}

    def document_digests(self) -> dict[str, str]:
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute("SELECT path, digest FROM documents").fetchall()
        except sqlite3.DatabaseError as exc:
            raise self._corruption_error(exc) from exc
        return {str(path): str(digest) for path, digest in rows}

    def document_count(self) -> int:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute("SELECT COUNT(*) FROM documents").fetchone()
        except sqlite3.DatabaseError as exc:
            raise self._corruption_error(exc) from exc
        return int(row[0]) if row is not None else 0

    def is_compatible(self, embedding_model: str, requested_dimensions: int | None) -> bool:
        values = self.metadata()
        expected_dimensions = "" if requested_dimensions is None else str(requested_dimensions)
        return (
            values.get("embedding_model") == embedding_model
            and values.get("requested_dimensions", "") == expected_dimensions
        )

    def apply_sync(
        self,
        document_digests: Mapping[str, str],
        indexed_chunks: Mapping[str, Sequence[tuple[Chunk, Sequence[float]]]],
        removed_paths: set[str],
        embedding_model: str,
        requested_dimensions: int | None,
        actual_dimensions: int | None,
        reset: bool,
    ) -> None:
        try:
            with closing(self._connect()) as connection:
                with connection:
                    if reset:
                        connection.execute("DELETE FROM documents")
                    else:
                        connection.executemany(
                            "DELETE FROM documents WHERE path = ?",
                            [(path,) for path in removed_paths],
                        )

                    for source_path, digest in document_digests.items():
                        connection.execute(
                            """
                            INSERT INTO documents(path, digest) VALUES (?, ?)
                            ON CONFLICT(path) DO UPDATE SET digest = excluded.digest
                            """,
                            (source_path, digest),
                        )

                    for source_path, chunks in indexed_chunks.items():
                        connection.execute("DELETE FROM chunks WHERE path = ?", (source_path,))
                        connection.executemany(
                            """
                            INSERT INTO chunks(
                                path, ordinal, start_line, end_line, text, vector_json
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            [
                                (
                                    source_path,
                                    ordinal,
                                    chunk.start_line,
                                    chunk.end_line,
                                    chunk.text,
                                    json.dumps(list(vector), separators=(",", ":")),
                                )
                                for ordinal, (chunk, vector) in enumerate(chunks)
                            ],
                        )

                    metadata_values = {
                        "embedding_model": embedding_model,
                        "requested_dimensions": (
                            "" if requested_dimensions is None else str(requested_dimensions)
                        ),
                        "actual_dimensions": ""
                        if actual_dimensions is None
                        else str(actual_dimensions),
                    }
                    connection.executemany(
                        """
                        INSERT INTO metadata(key, value) VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                        """,
                        list(metadata_values.items()),
                    )
        except sqlite3.DatabaseError as exc:
            raise self._corruption_error(exc) from exc
        if os.name != "nt":
            try:
                self.database_path.chmod(0o600)
            except OSError as exc:
                raise IndexCorruptionError(
                    "Cannot restrict permissions on the local index."
                ) from exc

    def search(
        self,
        query_vector: Sequence[float],
        embedding_model: str,
        requested_dimensions: int | None,
        top_k: int,
        minimum_similarity: float,
    ) -> list[SearchHit]:
        if not self.is_compatible(embedding_model, requested_dimensions):
            raise IndexCompatibilityError(
                "The saved index uses a different embedding model or dimension setting."
            )
        if not query_vector:
            return []

        values = self.metadata()
        stored_dimension = values.get("actual_dimensions", "")
        if stored_dimension and len(query_vector) != int(stored_dimension):
            raise IndexCompatibilityError(
                "The current embedding dimension differs from the saved index; "
                "rebuilding is required."
            )

        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT path, start_line, end_line, text, vector_json
                    FROM chunks
                    """
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise self._corruption_error(exc) from exc

        hits: list[SearchHit] = []
        for source_path, start_line, end_line, text, vector_json in rows:
            try:
                vector = json.loads(str(vector_json))
            except (json.JSONDecodeError, TypeError) as exc:
                raise IndexCorruptionError("A vector in the local index is malformed.") from exc
            if not isinstance(vector, list) or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) for value in vector
            ):
                raise IndexCorruptionError("A vector in the local index is malformed.")
            numeric_vector = [float(value) for value in vector]
            if any(not math.isfinite(value) for value in numeric_vector):
                raise IndexCorruptionError("A vector in the local index contains invalid values.")
            if len(numeric_vector) != len(query_vector):
                raise IndexCompatibilityError(
                    "Stored vectors have inconsistent dimensions; rebuilding is required."
                )
            score = cosine_similarity(query_vector, numeric_vector)
            if score >= minimum_similarity:
                hits.append(
                    SearchHit(
                        Chunk(
                            source_path=str(source_path),
                            start_line=int(start_line),
                            end_line=int(end_line),
                            text=str(text),
                        ),
                        score,
                    )
                )

        hits.sort(
            key=lambda hit: (
                -hit.score,
                hit.chunk.source_path,
                hit.chunk.start_line,
            )
        )
        return hits[:top_k]

    def _corruption_error(self, error: sqlite3.DatabaseError) -> IndexCorruptionError:
        return IndexCorruptionError(
            f"The local index at {self.database_path} is damaged. Remove it and restart."
        )


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)
