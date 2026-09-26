from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.invariants.domain.models.invariant import Invariant
from copia.sessions.domain.models.chat_session import ChatSession


def make_list_invariants(
    get_repository: Callable[[], InvariantsRepository],
    require_session: Callable[[str], Awaitable[ChatSession]],
) -> tuple[
    Callable[[], Awaitable[list[Invariant]]],
    Callable[[str], Awaitable[list[Invariant]]],
]:
    async def list_invariants() -> list[Invariant]:
        try:
            return await run_in_threadpool(get_repository().load)
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=500, detail="Invariants are unavailable") from error

    async def list_session_invariants(session_id: str) -> list[Invariant]:
        await require_session(session_id)
        return await list_invariants()

    return list_invariants, list_session_invariants
