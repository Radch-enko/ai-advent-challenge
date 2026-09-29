from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from copia.conversations.api.models.conversation_command import (
    CompletionCommand,
    ConversationCommand,
    RetrySummarizationCommand,
    SendMessageCommand,
)
from copia.conversations.application.conversation_run import ConversationRun
from copia.providers.data.llm import ProviderError


@dataclass(frozen=True)
class ConversationOperations:
    message: Callable[
        [ConversationRun, SendMessageCommand, Callable[[str, dict[str, Any]], None]],
        Awaitable[Any],
    ]
    completion: Callable[
        [ConversationRun, CompletionCommand, Callable[[str, dict[str, Any]], None]], Awaitable[Any]
    ]
    retry_summarization: Callable[
        [ConversationRun, RetrySummarizationCommand, Callable[[str, dict[str, Any]], None]],
        Awaitable[Any],
    ]


class ConversationService:
    def __init__(self, operations: ConversationOperations) -> None:
        self._operations = operations

    async def execute(self, run: ConversationRun, command: ConversationCommand) -> None:
        run.emit("message.started", {"conversation_id": run.id})
        emit = run.emit
        try:
            if isinstance(command, SendMessageCommand):
                result = await self._operations.message(run, command, emit)
            elif isinstance(command, CompletionCommand):
                result = await self._operations.completion(run, command, emit)
            elif isinstance(command, RetrySummarizationCommand):
                result = await self._operations.retry_summarization(run, command, emit)
            else:
                raise ValueError("Unsupported conversation command")
            payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
            run.emit("conversation.completed", {"conversation_id": run.id, "result": payload})
        except HTTPException as error:
            if run.status in {"completed", "failed"}:
                return
            detail = error.detail if isinstance(error.detail, dict) else {}
            code = detail.get(
                "code",
                "provider_request_failed" if error.status_code == 502 else "conversation_failed",
            )
            message = detail.get("message", "Conversation could not be completed")
            run.emit(
                "conversation.failed",
                {
                    "conversation_id": run.id,
                    "code": code,
                    "message": message,
                    "http_status": error.status_code,
                },
            )
        except ProviderError:
            if run.status in {"completed", "failed"}:
                return
            run.emit(
                "conversation.failed",
                {
                    "conversation_id": run.id,
                    "code": "provider_request_failed",
                    "message": "Provider request failed",
                },
            )
        except Exception:
            if run.status in {"completed", "failed"}:
                return
            run.emit(
                "conversation.failed",
                {
                    "conversation_id": run.id,
                    "code": "conversation_failed",
                    "message": "Conversation could not be completed",
                },
            )
