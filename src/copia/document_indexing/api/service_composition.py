from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from copia.document_indexing.api.routes import DocumentIndexingRoutes
from copia.document_indexing.application.document_indexer import DocumentIndexer
from copia.document_indexing.application.document_retriever import DocumentRetriever
from copia.document_indexing.data.document_loader import DocumentLoader
from copia.document_indexing.data.embedding_settings_repository import (
    EmbeddingSettingsRepository,
)
from copia.document_indexing.data.index_artifact_store import IndexArtifactStore
from copia.providers.application.embedding_router import EmbeddingRouter
from copia.providers.application.llm_router import LLMRouter


class DocumentIndexingServiceComposition:
    def __init__(
        self,
        data_root: Path,
        documents_path: Path,
        providers: EmbeddingRouter,
        llm_router: LLMRouter | None = None,
    ) -> None:
        resolved_root = data_root.expanduser().resolve()
        resolved_documents = documents_path.expanduser().resolve()
        self.providers = providers
        self.artifact_store = IndexArtifactStore(resolved_root / "document-index")
        self.indexer = DocumentIndexer(
            DocumentLoader(resolved_documents),
            self.artifact_store,
            providers,
        )
        self.retriever = DocumentRetriever(self.artifact_store, providers, llm_router)
        self.settings_repository = EmbeddingSettingsRepository(
            resolved_root / "document-index" / "settings.json"
        )
        self._routes = DocumentIndexingRoutes(
            self.settings_repository,
            self.indexer,
            providers,
            str(resolved_documents),
            str((resolved_root / "document-index").resolve()),
        )

    def router(self) -> APIRouter:
        return self._routes.router()

    def close(self) -> None:
        self.indexer.close()
        self.providers.close()
