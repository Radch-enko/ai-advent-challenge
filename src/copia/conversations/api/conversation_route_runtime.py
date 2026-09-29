from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from copia.conversations.api.models.conversation_command import ConversationCommand
from copia.conversations.application.conversation_run import ConversationRun
from copia.conversations.application.conversation_store import ConversationStore


@dataclass(frozen=True)
class ConversationRouteRuntime:
    store: ConversationStore
    validate: Callable[[ConversationCommand], Awaitable[None]]
    execute: Callable[[ConversationRun, ConversationCommand], Awaitable[None]]
    decide_approval: Callable[[str, str, str], Awaitable[dict[str, Any]]]
