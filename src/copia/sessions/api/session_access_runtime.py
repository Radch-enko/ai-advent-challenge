from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from copia.sessions.data.sessions_repository import SessionsRepository


@dataclass(frozen=True)
class SessionAccessRuntime:
    sessions: SessionsRepository
    threadpool: Callable[..., Awaitable[Any]]
    lifecycle_lock: AbstractContextManager[Any]
    message_locks: MutableMapping[str, object]
