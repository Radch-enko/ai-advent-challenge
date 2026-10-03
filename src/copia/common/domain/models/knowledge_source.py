from __future__ import annotations

from pydantic import BaseModel, Field, SerializerFunctionWrapHandler, model_serializer


class KnowledgeSource(BaseModel):
    chunk_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    title: str = Field(min_length=1)
    section: str = ""
    similarity_score: float | None = Field(default=None, ge=-1, le=1)
    selected_for_context: bool | None = None
    quote: str | None = None

    @model_serializer(mode="wrap")
    def omit_unset_rag_metadata(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data = handler(self)
        if self.similarity_score is None:
            data.pop("similarity_score", None)
        if self.selected_for_context is None:
            data.pop("selected_for_context", None)
        if self.quote is None:
            data.pop("quote", None)
        return data
