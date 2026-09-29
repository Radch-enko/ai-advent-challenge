from __future__ import annotations

import logging
import threading
from _thread import LockType
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import cast

from fastapi import HTTPException, status

from copia.sessions.api.session_access_runtime import SessionAccessRuntime
from copia.sessions.application.models.session_lock_state import SessionLockState
from copia.sessions.domain.models.chat_session import ChatSession
from copia.storage.domain.services.path_identifiers import validate_path_identifier

logger = logging.getLogger(__name__)


class SessionAccess:
    def __init__(self, get_runtime: Callable[[], SessionAccessRuntime]) -> None:
        self._get_runtime = get_runtime

    def get_session_locked(self, session_id: str) -> ChatSession:
        self._validate_session_id(session_id)
        session = self._get_runtime().sessions.load(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
        return session

    async def get_session(self, session_id: str) -> ChatSession:
        self._validate_session_id(session_id)
        runtime = self._get_runtime()
        session = await runtime.threadpool(runtime.sessions.load, session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
        return session

    def session_message_lock(self, session_id: str) -> SessionLockState:
        self._validate_session_id(session_id)
        runtime = self._get_runtime()
        with runtime.lifecycle_lock:
            existing = runtime.message_locks.get(session_id)
            if isinstance(existing, SessionLockState):
                state = existing
            else:
                state = SessionLockState(
                    session_id=session_id,
                    lock=cast(LockType, existing or threading.Lock()),
                )
                runtime.message_locks[session_id] = state
            state.users += 1
            return state

    def release_session_message_lock(self, state: SessionLockState) -> None:
        runtime = self._get_runtime()
        on_idle: list[Callable[[], None]] = []
        with runtime.lifecycle_lock:
            state.users -= 1
            if state.retired and state.users == 0:
                runtime.message_locks.pop(state.session_id, None)
                on_idle = list(state.on_idle)
                state.on_idle.clear()
        for callback in on_idle:
            try:
                callback()
            except OSError:
                logger.exception("Deferred cleanup for a retired session failed")

    @contextmanager
    def session_mutation_lock(self, session_id: str) -> Iterator[None]:
        message_lock = self.session_message_lock(session_id)
        message_lock.lock.acquire()
        try:
            with self._get_runtime().lifecycle_lock:
                yield
        finally:
            message_lock.lock.release()
            self.release_session_message_lock(message_lock)

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        try:
            validate_path_identifier(session_id, "session ID")
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid session ID") from error
