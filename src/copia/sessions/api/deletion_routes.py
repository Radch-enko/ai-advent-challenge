from collections.abc import Callable, MutableMapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, status

from copia.sessions.data.sessions_repository import SessionsRepository


class SessionLockState(Protocol):
    lock: Any
    retired: bool
    on_idle: list[Callable[[], None]]


class SessionDeletionRoutes:
    def __init__(
        self,
        get_repository: Callable[[], SessionsRepository],
        delete_working_memory: Callable[[str], None],
        delete_pending_memory: Callable[[str], None],
        get_pending_cache: Callable[[], MutableMapping[str, Any]],
        get_approved_cache: Callable[[], MutableMapping[tuple[str, str], Any]],
        acquire_message_lock: Callable[[str], SessionLockState],
        release_message_lock: Callable[[SessionLockState], None],
        get_lifecycle_lock: Callable[[], AbstractContextManager[Any]],
    ) -> None:
        self._get_repository = get_repository
        self._delete_working_memory = delete_working_memory
        self._delete_pending_memory = delete_pending_memory
        self._get_pending_cache = get_pending_cache
        self._get_approved_cache = get_approved_cache
        self._acquire_message_lock = acquire_message_lock
        self._release_message_lock = release_message_lock
        self._get_lifecycle_lock = get_lifecycle_lock

    def delete_session(self, session_id: str) -> None:
        message_lock = self._acquire_message_lock(session_id)
        try:
            with self._get_lifecycle_lock():
                message_lock.retired = True
                repository = self._get_repository()
                detached = repository.detach(session_id)
                if detached is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session"
                    )
                if message_lock.lock.locked():
                    message_lock.on_idle.append(
                        lambda: self._finalize_delete(repository, detached, session_id)
                    )
                else:
                    self._cleanup_session_data(session_id)
                    repository.finalize_delete(detached)
        finally:
            self._release_message_lock(message_lock)

    def _finalize_delete(
        self, repository: SessionsRepository, detached: Path, session_id: str
    ) -> None:
        self._cleanup_session_data(session_id)
        repository.delete(session_id)
        repository.finalize_delete(detached)

    def _cleanup_session_data(self, session_id: str) -> None:
        self._delete_working_memory(session_id)
        self._delete_pending_memory(session_id)
        self._get_pending_cache().pop(session_id, None)
        approved = self._get_approved_cache()
        for key in [key for key in approved if key[0] == session_id]:
            approved.pop(key, None)

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}",
            self.delete_session,
            methods=["DELETE"],
            status_code=status.HTTP_204_NO_CONTENT,
        )
        return router
