from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.invariants.domain.models.invariant import Invariant
from copia.invariants.domain.models.invariant_update import InvariantUpdate
from copia.sessions.domain.models.chat_session import ChatSession


def make_update_invariant(
    get_repository: Callable[[], InvariantsRepository],
    require_session: Callable[[str], Awaitable[ChatSession]],
) -> tuple[
    Callable[[str, InvariantUpdate], Awaitable[Invariant]],
    Callable[[str, str, InvariantUpdate], Awaitable[Invariant]],
]:
    def save_invariant(item_id: str, request: InvariantUpdate) -> Invariant:
        try:
            return get_repository().update(
                item_id,
                {**request.model_dump(exclude_none=True), "updated_at": datetime.now(UTC)},
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Unknown invariant") from error

    async def update_invariant(item_id: str, request: InvariantUpdate) -> Invariant:
        return await run_in_threadpool(save_invariant, item_id, request)

    async def update_session_invariant(
        session_id: str, item_id: str, request: InvariantUpdate
    ) -> Invariant:
        await require_session(session_id)
        return await update_invariant(item_id, request)

    return update_invariant, update_session_invariant
