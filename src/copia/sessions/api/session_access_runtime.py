from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from copia.sessions.data.sessions_repository import SessionsRepository


@dataclass(frozen=True)
class SessionAccessRuntime:
    sessions: SessionsRepository
    threadpool: Callable[..., Awaitable[Any]]
    mcp_turns: Mapping[str, object]
    mcp_turns_lock: AbstractContextManager[Any]
    lifecycle_lock: AbstractContextManager[Any]
    message_locks: MutableMapping[str, object]
