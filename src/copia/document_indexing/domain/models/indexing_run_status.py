from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class IndexingRunStatus(BaseModel):
    run_id: str | None = None
    state: Literal["idle", "running", "completed", "failed"] = "idle"
    stage: str = "idle"
    processed_files: int = 0
    total_files: int = 0
    error: str | None = None
    artifact_path: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
