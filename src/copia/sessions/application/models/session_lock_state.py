from __future__ import annotations

from _thread import LockType
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class SessionLockState:
    session_id: str
    lock: LockType
    users: int = 0
    retired: bool = False
    on_idle: list[Callable[[], None]] = field(default_factory=list)
