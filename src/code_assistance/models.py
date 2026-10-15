from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    path: str
    text: str
    digest: str


@dataclass(frozen=True)
class Chunk:
    source_path: str
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class BranchContext:
    branch: str | None
    detached: bool
    commit_sha: str | None


@dataclass(frozen=True)
class GitEvidence:
    reference: str
    text: str


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, object]
