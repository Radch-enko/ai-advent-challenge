from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from copia.document_indexing.api.models.embedding_provider_response import (
    EmbeddingProviderResponse,
    EmbeddingProvidersResponse,
)
from copia.document_indexing.api.models.embedding_settings_request import (
    EmbeddingSettingsRequest,
)
from copia.document_indexing.api.models.embedding_settings_response import (
    EmbeddingSettingsResponse,
)
from copia.document_indexing.api.models.latest_index_response import LatestIndexResponse
from copia.document_indexing.application.document_indexer import DocumentIndexer
from copia.document_indexing.data.embedding_settings_repository import (
    EmbeddingSettingsRepository,
)
from copia.document_indexing.domain.errors import DocumentIndexingError, IndexRunConflict
from copia.document_indexing.domain.models.embedding_settings import EmbeddingSettings
from copia.document_indexing.domain.models.indexing_run_status import IndexingRunStatus
from copia.providers.application.embedding_router import EmbeddingRouter
from copia.providers.domain.errors import ProviderError


class DocumentIndexingRoutes:
    def __init__(
        self,
        settings_repository: EmbeddingSettingsRepository,
        indexer: DocumentIndexer,
        providers: EmbeddingRouter,
        source_path: str,
        artifact_root: str,
    ) -> None:
        self._settings = settings_repository
        self._indexer = indexer
        self._providers = providers
        self._source_path = source_path
        self._artifact_root = artifact_root

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/document-indexing", tags=["document-indexing"])

        @router.get("/settings", response_model=EmbeddingSettingsResponse)
        def get_settings() -> EmbeddingSettingsResponse:
            settings = self._settings.load()
            return self._settings_response(settings)

        @router.put("/settings", response_model=EmbeddingSettingsResponse)
        def update_settings(request: EmbeddingSettingsRequest) -> EmbeddingSettingsResponse:
            try:
                self._providers.provider(request.provider)
            except ProviderError as error:
                raise HTTPException(
                    status_code=422, detail="Unsupported embedding provider"
                ) from error
            model = request.model.strip()
            if not model:
                raise HTTPException(status_code=422, detail="Embedding model is required")
            settings = self._settings.save(
                EmbeddingSettings(provider=request.provider, model=model)
            )
            return self._settings_response(settings)

        @router.get("/embedding-providers", response_model=EmbeddingProvidersResponse)
        async def list_embedding_providers() -> EmbeddingProvidersResponse:
            provider_options: list[EmbeddingProviderResponse] = []
            for info in self._providers.providers():
                provider = self._providers.provider(info.id)
                models: list[str] = []
                models_error: str | None = None
                if provider.is_configured:
                    try:
                        models = await run_in_threadpool(provider.list_models)
                    except ProviderError:
                        models_error = "Embedding models could not be loaded"
                provider_options.append(
                    EmbeddingProviderResponse(
                        id=info.id,
                        display_name=info.display_name,
                        default_model=info.default_model,
                        configured=provider.is_configured,
                        models=models,
                        models_error=models_error,
                    )
                )
            return EmbeddingProvidersResponse(providers=provider_options)

        @router.post(
            "/runs", status_code=status.HTTP_202_ACCEPTED, response_model=IndexingRunStatus
        )
        def start_indexing() -> IndexingRunStatus:
            settings = self._settings.load()
            try:
                return self._indexer.start(settings)
            except IndexRunConflict as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            except ProviderError as error:
                raise HTTPException(
                    status_code=503,
                    detail="The selected embedding provider is not configured",
                ) from error
            except (DocumentIndexingError, OSError) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error

        @router.get("/runs/current", response_model=IndexingRunStatus)
        def get_current_run_status() -> IndexingRunStatus:
            return self._indexer.current_status()

        @router.get("/runs/{run_id}", response_model=IndexingRunStatus)
        def get_run_status(run_id: str) -> IndexingRunStatus:
            run = self._indexer.status(run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Indexing run was not found")
            return run

        @router.get("/latest", response_model=LatestIndexResponse | None)
        def get_latest_index() -> LatestIndexResponse | None:
            try:
                latest = self._indexer.latest()
            except (DocumentIndexingError, OSError) as error:
                raise HTTPException(
                    status_code=500, detail="Latest document index is unavailable"
                ) from error
            return LatestIndexResponse(**latest) if latest is not None else None

        return router

    def _settings_response(self, settings: EmbeddingSettings) -> EmbeddingSettingsResponse:
        source_file_count, source_bytes = self._indexer.source_summary()
        return EmbeddingSettingsResponse(
            provider=settings.provider,
            model=settings.model,
            source_path=self._source_path,
            artifact_root=self._artifact_root,
            source_file_count=source_file_count,
            source_bytes=source_bytes,
        )
