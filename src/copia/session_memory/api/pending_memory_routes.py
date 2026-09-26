import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.session_memory.api.models.long_term_memory_mutation_response import (
    LongTermMemoryMutationResponse,
)
from copia.session_memory.api.models.working_memory_collection_response import (
    WorkingMemoryCollectionResponse,
)
from copia.session_memory.api.threadpool import ThreadpoolRunner
from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.domain.models.memory_candidate import MemoryCandidate
from copia.session_memory.domain.models.memory_event import MemoryEvent
from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.sessions.domain.models.chat_session import ChatSession
from copia.storage.domain.services.path_identifiers import validate_path_identifier


class PendingMemoryRoutes:
    def __init__(
        self,
        get_repository: Callable[[], PendingMemoryRepository],
        get_profile_repository: Callable[[], ProfileMemoryRepository],
        get_pending_cache: Callable[[], dict[str, list[PendingMemorySuggestion]]],
        get_approved_cache: Callable[[], dict[tuple[str, str], LongTermMemoryMutationResponse]],
        cache_approved: Callable[[tuple[str, str], LongTermMemoryMutationResponse], None],
        require_session: Callable[[str], Awaitable[ChatSession]],
        get_session_locked: Callable[[str], ChatSession],
        mutation_lock: Callable[[str], AbstractContextManager[Any]],
        get_threadpool: Callable[[], ThreadpoolRunner],
    ) -> None:
        self._get_repository = get_repository
        self._get_profile_repository = get_profile_repository
        self._get_pending_cache = get_pending_cache
        self._get_approved_cache = get_approved_cache
        self._cache_approved = cache_approved
        self._require_session = require_session
        self._get_session_locked = get_session_locked
        self._mutation_lock = mutation_lock
        self._get_threadpool = get_threadpool

    async def list_pending_memory(self, session_id: str) -> list[PendingMemorySuggestion]:
        await self._require_session(session_id)
        return await self._get_threadpool()(self._get_repository().load, session_id)

    async def approve_memory(
        self, session_id: str, candidate_id: str
    ) -> LongTermMemoryMutationResponse:
        return await self._get_threadpool()(self._approve_memory, session_id, candidate_id)

    def _approve_memory(self, session_id: str, candidate_id: str) -> LongTermMemoryMutationResponse:
        with self._mutation_lock(session_id):
            session = self._get_session_locked(session_id)
            try:
                validate_path_identifier(candidate_id, "candidate ID")
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Invalid candidate ID") from error
            if session.profile_name is None:
                raise HTTPException(
                    status_code=409, detail="Long-term memory is unavailable without a profile"
                )
            cached = self._get_approved_cache().get((session_id, candidate_id))
            if cached is not None:
                return cached
            repository = self._get_repository()
            suggestions = repository.load(session_id)
            suggestion = next((item for item in suggestions if item.id == candidate_id), None)
            if suggestion is None or (
                suggestion.candidate.action in {"create", "update"}
                and suggestion.candidate.value is None
            ):
                raise HTTPException(status_code=404, detail="Unknown pending memory suggestion")
            candidate = suggestion.candidate
            if candidate.scope != "long_term" or candidate.action not in {
                "create",
                "update",
                "delete",
            }:
                raise HTTPException(status_code=409, detail="Invalid long-term memory suggestion")
            item = self._apply_candidate(session.profile_name, candidate)
            remaining = [current for current in suggestions if current.id != candidate_id]
            repository.save(session_id, remaining)
            self._get_pending_cache()[session_id] = remaining
            result = LongTermMemoryMutationResponse(
                **item.model_dump(),
                memory_events=[
                    MemoryEvent(
                        id=str(uuid.uuid4()),
                        scope="long_term",
                        action="approved",
                        key=item.key,
                        candidate_id=candidate_id,
                    )
                ],
            )
            self._cache_approved((session_id, candidate_id), result)
            return result

    def _apply_candidate(self, profile_name: str, candidate: MemoryCandidate) -> LongTermMemoryItem:
        repository = self._get_profile_repository()
        existing = repository.load(profile_name)
        target = next((item for item in existing if item.id == candidate.target_id), None)
        if candidate.action == "delete":
            return self._delete_candidate(repository, profile_name, candidate, target)
        if candidate.action == "update":
            return self._update_candidate(repository, profile_name, candidate, target)
        return self._create_candidate(repository, profile_name, candidate, existing)

    def _delete_candidate(
        self,
        repository: ProfileMemoryRepository,
        profile_name: str,
        candidate: MemoryCandidate,
        target: LongTermMemoryItem | None,
    ) -> LongTermMemoryItem:
        if candidate.target_id is None:
            raise HTTPException(status_code=409, detail="Delete suggestions require a target")
        if target is None:
            raise HTTPException(status_code=404, detail="Unknown long-term memory target")
        repository.delete_item(profile_name, target.id)
        return target

    def _update_candidate(
        self,
        repository: ProfileMemoryRepository,
        profile_name: str,
        candidate: MemoryCandidate,
        target: LongTermMemoryItem | None,
    ) -> LongTermMemoryItem:
        if candidate.target_id is None:
            raise HTTPException(status_code=409, detail="Update suggestions require a target")
        if target is None:
            raise HTTPException(status_code=404, detail="Unknown long-term memory target")
        return repository.update(
            profile_name,
            target.id,
            {
                "category": candidate.category,
                "key": candidate.key,
                "value": candidate.value,
                "updated_at": datetime.now(UTC),
            },
        )

    def _create_candidate(
        self,
        repository: ProfileMemoryRepository,
        profile_name: str,
        candidate: MemoryCandidate,
        existing: list[LongTermMemoryItem],
    ) -> LongTermMemoryItem:
        if candidate.target_id is not None or any(item.key == candidate.key for item in existing):
            raise HTTPException(
                status_code=409, detail="Create suggestion conflicts with existing memory"
            )
        now = datetime.now(UTC)
        item = LongTermMemoryItem(
            id=str(uuid.uuid4()),
            category=candidate.category,
            key=candidate.key,
            value=candidate.value or "",
            created_at=now,
            updated_at=now,
        )
        repository.create(profile_name, item)
        return item

    async def reject_memory(
        self, session_id: str, candidate_id: str
    ) -> WorkingMemoryCollectionResponse:
        return await self._get_threadpool()(self._reject_memory, session_id, candidate_id)

    def _reject_memory(self, session_id: str, candidate_id: str) -> WorkingMemoryCollectionResponse:
        with self._mutation_lock(session_id):
            self._get_session_locked(session_id)
            try:
                validate_path_identifier(candidate_id, "candidate ID")
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Invalid candidate ID") from error
            suggestions = self._get_repository().load(session_id)
            if not any(item.id == candidate_id for item in suggestions):
                return WorkingMemoryCollectionResponse()
            remaining = [item for item in suggestions if item.id != candidate_id]
            self._get_repository().save(session_id, remaining)
            self._get_pending_cache()[session_id] = remaining
            return WorkingMemoryCollectionResponse(
                memory_events=[
                    MemoryEvent(
                        id=str(uuid.uuid4()),
                        scope="long_term",
                        action="rejected",
                        candidate_id=candidate_id,
                    )
                ]
            )

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}/memory/pending",
            self.list_pending_memory,
            methods=["GET"],
            response_model=list[PendingMemorySuggestion],
        )
        router.add_api_route(
            "/sessions/{session_id}/memory/pending/{candidate_id}/approve",
            self.approve_memory,
            methods=["POST"],
            response_model=LongTermMemoryMutationResponse,
        )
        router.add_api_route(
            "/sessions/{session_id}/memory/pending/{candidate_id}/reject",
            self.reject_memory,
            methods=["POST"],
            response_model=WorkingMemoryCollectionResponse,
        )
        return router
