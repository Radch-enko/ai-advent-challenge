from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.sessions.domain.models.chat_session import ChatSession


def make_delete_invariant(
    get_repository: Callable[[], InvariantsRepository],
    require_session: Callable[[str], Awaitable[ChatSession]],
) -> tuple[
    Callable[[str], Awaitable[None]],
    Callable[[str, str], Awaitable[None]],
]:
    def remove_invariant(item_id: str) -> None:
        try:
            get_repository().delete_item(item_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Unknown invariant") from error

    async def delete_invariant(item_id: str) -> None:
        return await run_in_threadpool(remove_invariant, item_id)

    async def delete_session_invariant(session_id: str, item_id: str) -> None:
        await require_session(session_id)
        return await delete_invariant(item_id)

    return delete_invariant, delete_session_invariant
