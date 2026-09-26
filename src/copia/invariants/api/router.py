from collections.abc import Awaitable, Callable

from fastapi import APIRouter, status

from copia.invariants.api.create_invariant import make_create_invariant
from copia.invariants.api.delete_invariant import make_delete_invariant
from copia.invariants.api.list_invariants import make_list_invariants
from copia.invariants.api.update_invariant import make_update_invariant
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.invariants.domain.models.invariant import Invariant
from copia.sessions.domain.models.chat_session import ChatSession


def create_invariants_router(
    get_repository: Callable[[], InvariantsRepository],
    require_session: Callable[[str], Awaitable[ChatSession]],
) -> APIRouter:
    router = APIRouter()
    list_invariants, list_session_invariants = make_list_invariants(get_repository, require_session)
    create_invariant, create_session_invariant = make_create_invariant(
        get_repository, require_session
    )
    update_invariant, update_session_invariant = make_update_invariant(
        get_repository, require_session
    )
    delete_invariant, delete_session_invariant = make_delete_invariant(
        get_repository, require_session
    )

    router.add_api_route(
        "/invariants", list_invariants, methods=["GET"], response_model=list[Invariant]
    )
    router.add_api_route(
        "/sessions/{session_id}/invariants",
        list_session_invariants,
        methods=["GET"],
        response_model=list[Invariant],
    )
    router.add_api_route(
        "/invariants",
        create_invariant,
        methods=["POST"],
        response_model=Invariant,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        "/sessions/{session_id}/invariants",
        create_session_invariant,
        methods=["POST"],
        response_model=Invariant,
        status_code=201,
    )
    router.add_api_route(
        "/invariants/{item_id}", update_invariant, methods=["PATCH"], response_model=Invariant
    )
    router.add_api_route(
        "/sessions/{session_id}/invariants/{item_id}",
        update_session_invariant,
        methods=["PATCH"],
        response_model=Invariant,
    )
    router.add_api_route(
        "/invariants/{item_id}", delete_invariant, methods=["DELETE"], status_code=204
    )
    router.add_api_route(
        "/sessions/{session_id}/invariants/{item_id}",
        delete_session_invariant,
        methods=["DELETE"],
        status_code=204,
    )
    return router
