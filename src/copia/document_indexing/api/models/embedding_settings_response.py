from pydantic import BaseModel


class EmbeddingSettingsResponse(BaseModel):
    provider: str
    model: str
    source_path: str
    artifact_root: str
    source_file_count: int
    source_bytes: int
