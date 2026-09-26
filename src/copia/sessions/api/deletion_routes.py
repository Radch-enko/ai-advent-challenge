from collections.abc import Callable, MutableMapping
from contextlib import AbstractContextManager
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, status

from copia.sessions.data.sessions_repository import SessionsRepository


class SessionLockState(Protocol):
    lock: Any
    retired: bool


class SessionDeletionRoutes:
    def __init__(
        self,
        get_repository: Callable[[], SessionsRepository],
        delete_agent_logs: Callable[[str], None],
        delete_working_memory: Callable[[str], None],
        delete_pending_memory: Callable[[str], None],
        get_pending_cache: Callable[[], MutableMapping[str, Any]],
        get_approved_cache: Callable[[], MutableMapping[tuple[str, str], Any]],
        acquire_message_lock: Callable[[str], SessionLockState],
        release_message_lock: Callable[[SessionLockState], None],
        get_lifecycle_lock: Callable[[], AbstractContextManager[Any]],
    ) -> None:
        self._get_repository = get_repository
        self._delete_agent_logs = delete_agent_logs
        self._delete_working_memory = delete_working_memory
        self._delete_pending_memory = delete_pending_memory
        self._get_pending_cache = get_pending_cache
        self._get_approved_cache = get_approved_cache
        self._acquire_message_lock = acquire_message_lock
        self._release_message_lock = release_message_lock
        self._get_lifecycle_lock = get_lifecycle_lock

    def delete_session(self, session_id: str) -> None:
        # Сначала блокируем сообщения, затем операции с жизненным циклом сессии.
        message_lock = self._acquire_message_lock(session_id)
        message_lock.lock.acquire()
        try:
            with self._get_lifecycle_lock():
                message_lock.retired = True
                if not self._get_repository().delete(session_id):
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session"
                    )
                self._delete_agent_logs(session_id)
                self._delete_working_memory(session_id)
                self._delete_pending_memory(session_id)
                self._get_pending_cache().pop(session_id, None)
                approved = self._get_approved_cache()
                for key in [key for key in approved if key[0] == session_id]:
                    approved.pop(key, None)
        finally:
            message_lock.lock.release()
            self._release_message_lock(message_lock)

    def router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(
            "/sessions/{session_id}",
            self.delete_session,
            methods=["DELETE"],
            status_code=status.HTTP_204_NO_CONTENT,
        )
        return router
