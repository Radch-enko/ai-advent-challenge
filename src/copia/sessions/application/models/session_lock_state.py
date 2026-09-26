from __future__ import annotations

from _thread import LockType
from dataclasses import dataclass


@dataclass
class SessionLockState:
    session_id: str
    lock: LockType
    users: int = 0
    retired: bool = False
