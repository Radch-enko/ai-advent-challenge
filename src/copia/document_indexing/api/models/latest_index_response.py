from typing import Any

from pydantic import BaseModel


class LatestIndexResponse(BaseModel):
    manifest: dict[str, Any]
    artifact_path: str
    comparison: str
