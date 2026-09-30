from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from copia.document_indexing.api.routes import DocumentIndexingRoutes
from copia.document_indexing.application.document_indexer import DocumentIndexer
from copia.document_indexing.data.document_loader import DocumentLoader
from copia.document_indexing.data.embedding_settings_repository import (
    EmbeddingSettingsRepository,
)
from copia.document_indexing.data.index_artifact_store import IndexArtifactStore
from copia.providers.application.embedding_router import EmbeddingRouter


class DocumentIndexingServiceComposition:
    def __init__(
        self,
        data_root: Path,
        documents_path: Path,
        providers: EmbeddingRouter,
    ) -> None:
        resolved_root = data_root.expanduser().resolve()
        resolved_documents = documents_path.expanduser().resolve()
        self.providers = providers
        self.indexer = DocumentIndexer(
            DocumentLoader(resolved_documents),
            IndexArtifactStore(resolved_root / "document-index"),
            providers,
        )
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
