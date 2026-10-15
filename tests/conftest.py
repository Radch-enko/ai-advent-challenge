import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def git_repository(tmp_path: Path) -> Iterator[Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    yield repository


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.dimensions: list[int | None] = []

    def embed(
        self,
        texts: list[str] | tuple[str, ...],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        self.calls.append(list(texts))
        self.dimensions.append(dimensions)
        vectors = [self.vector(text) for text in texts]
        if dimensions is None:
            return vectors
        return [(vector + [0.0] * dimensions)[:dimensions] for vector in vectors]

    @staticmethod
    def vector(text: str) -> list[float]:
        lowered = text.casefold()
        if any(word in lowered for word in ("layout", "structure", "architecture")):
            return [1.0, 0.0]
        if any(word in lowered for word in ("payment", "billing", "invoice")):
            return [0.0, 1.0]
        return [0.0, 0.0]


@pytest.fixture
def fake_embeddings() -> FakeEmbeddings:
    return FakeEmbeddings()
