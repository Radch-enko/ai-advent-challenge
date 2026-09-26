import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from copia.profile_memory.domain.models.long_term_memory_update import LongTermMemoryUpdate
from copia.session_memory.api.models.working_memory_collection_response import (
    WorkingMemoryCollectionResponse,
)
from copia.session_memory.api.models.working_memory_mutation_response import (
    WorkingMemoryMutationResponse,
)
from copia.session_memory.api.threadpool import ThreadpoolRunner
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.session_memory.domain.models.memory_event import MemoryEvent
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.domain.models.chat_session import ChatSession


class WorkingMemoryRoutes:
    def __init__(
        self,
        get_repository: Callable[[], WorkingMemoryRepository],
        require_session: Callable[[str], Awaitable[ChatSession]],
        get_session_locked: Callable[[str], ChatSession],
        mutation_lock: Callable[[str], AbstractContextManager[Any]],
        get_threadpool: Callable[[], ThreadpoolRunner],
    ) -> None:
        self._get_repository = get_repository
        self._require_session = require_session
        self._get_session_locked = get_session_locked
        self._mutation_lock = mutation_lock
        self._get_threadpool = get_threadpool

    async def list_working_memory(self, session_id: str) -> list[WorkingMemoryItem]:
        await self._require_session(session_id)
        try:
            return await self._get_threadpool()(self._get_repository().load, session_id)
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=500, detail="Working memory is unavailable") from error

    async def update_working_memory(
        self, session_id: str, item_id: str, request: LongTermMemoryUpdate
    ) -> WorkingMemoryMutationResponse:
        return await self._get_threadpool()(
            self._update_working_memory, session_id, item_id, request
        )

    def _update_working_memory(
        self, session_id: str, item_id: str, request: LongTermMemoryUpdate
    ) -> WorkingMemoryMutationResponse:
        with self._mutation_lock(session_id):
            self._get_session_locked(session_id)
            repository = self._get_repository()
            items = repository.load(session_id)
            for index, item in enumerate(items):
                if item.id == item_id:
                    updated = item.model_copy(
                        update={
                            **request.model_dump(exclude_none=True),
                            "updated_at": datetime.now(UTC),
                        }
                    )
                    items[index] = updated
                    repository.save(session_id, items)
                    return WorkingMemoryMutationResponse(
                        **updated.model_dump(),
                        memory_events=[
                            MemoryEvent(
                                id=str(uuid.uuid4()),
                                scope="working",
                                action="updated",
                                key=updated.key,
                            )
                        ],
                    )
            raise HTTPException(status_code=404, detail="Unknown working memory item")

    async def delete_working_memory(
        self, session_id: str, item_id: str
    ) -> WorkingMemoryCollectionResponse:
        return await self._get_threadpool()(self._delete_working_memory, session_id, item_id)

    def _delete_working_memory(
        self, session_id: str, item_id: str
    ) -> WorkingMemoryCollectionResponse:
        with self._mutation_lock(session_id):
            self._get_session_locked(session_id)
            repository = self._get_repository()
            items = repository.load(session_id)
            deleted = next((item for item in items if item.id == item_id), None)
            retained = [item for item in items if item.id != item_id]
            if deleted is None:
                raise HTTPException(status_code=404, detail="Unknown working memory item")
            repository.save(session_id, retained)
            return WorkingMemoryCollectionResponse(
                working_memory=retained,
                memory_events=[
                    MemoryEvent(
                        id=str(uuid.uuid4()), scope="working", action="deleted", key=deleted.key
                    )
                ],
            )

    async def clear_working_memory(self, session_id: str) -> WorkingMemoryCollectionResponse:
        return await self._get_threadpool()(self._clear_working_memory, session_id)

    def _clear_working_memory(self, session_id: str) -> WorkingMemoryCollectionResponse:
        with self._mutation_lock(session_id):
            self._get_session_locked(session_id)
            self._get_repository().save(session_id, [])
            return WorkingMemoryCollectionResponse(
                memory_events=[MemoryEvent(id=str(uuid.uuid4()), scope="working", action="cleared")]
            )

    async def undo_working_memory(self, session_id: str) -> WorkingMemoryCollectionResponse:
        return await self._get_threadpool()(self._undo_working_memory, session_id)

    def _undo_working_memory(self, session_id: str) -> WorkingMemoryCollectionResponse:
        with self._mutation_lock(session_id):
            self._get_session_locked(session_id)
            restored = self._get_repository().undo_last(session_id)
            if restored is None:
                raise HTTPException(
                    status_code=404, detail="No automatic working memory change to undo"
                )
            return WorkingMemoryCollectionResponse(
                working_memory=restored,
                memory_events=[
                    MemoryEvent(
                        id=str(uuid.uuid4()),
                        scope="working",
                        action="updated",
                        message="Last automatic change undone",
                    )
                ],
            )

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/working-memory",
            self.list_working_memory,
            methods=["GET"],
            response_model=list[WorkingMemoryItem],
        )
        router.add_api_route(
            "/sessions/{session_id}/working-memory/{item_id}",
            self.update_working_memory,
            methods=["PATCH"],
            response_model=WorkingMemoryMutationResponse,
        )
        router.add_api_route(
            "/sessions/{session_id}/working-memory/{item_id}",
            self.delete_working_memory,
            methods=["DELETE"],
            response_model=WorkingMemoryCollectionResponse,
        )
        router.add_api_route(
            "/sessions/{session_id}/working-memory",
            self.clear_working_memory,
            methods=["DELETE"],
            response_model=WorkingMemoryCollectionResponse,
        )
        router.add_api_route(
            "/sessions/{session_id}/working-memory/undo",
            self.undo_working_memory,
            methods=["POST"],
            response_model=WorkingMemoryCollectionResponse,
        )
        return router
