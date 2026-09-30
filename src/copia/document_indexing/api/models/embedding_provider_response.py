from pydantic import BaseModel


class EmbeddingProviderResponse(BaseModel):
    id: str
    display_name: str
    default_model: str
    configured: bool
    models: list[str]
    models_error: str | None = None


class EmbeddingProvidersResponse(BaseModel):
    providers: list[EmbeddingProviderResponse]
