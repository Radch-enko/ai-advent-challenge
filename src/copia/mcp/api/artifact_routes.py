from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from copia.mcp.data.mcp_artifact_store import McpArtifactStore


class McpArtifactRoutes:
    def __init__(self, get_store: Callable[[], McpArtifactStore]) -> None:
        self._get_store = get_store

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/artifacts/{artifact_id}",
            self.get_artifact,
            methods=["GET"],
            response_class=FileResponse,
        )
        return router

    async def get_artifact(self, session_id: str, artifact_id: str) -> FileResponse:
        path = self._get_store().path(session_id, artifact_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return FileResponse(path, media_type="image/png", filename="expense-comparison.png")
