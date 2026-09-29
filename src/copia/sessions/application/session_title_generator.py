from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from copia.common.domain.services.llm_context_builder import LLMContextBuilder
from copia.common.domain.services.prompt_resources import render_prompt
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.providers.application.llm_router import LLMRouter
from copia.providers.data.llm import ProviderError
from copia.providers.domain.models.generation_config import GenerationConfig
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.structured_output_config import StructuredOutputConfig
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.services.context_rendering import render_invariants_context


class SessionTitleGenerator:
    def __init__(
        self,
        get_sessions: Callable[[], SessionsRepository],
        get_invariants: Callable[[], InvariantsRepository],
        get_router: Callable[[], LLMRouter],
        get_lifecycle_lock: Callable[[], AbstractContextManager[Any]],
    ) -> None:
        self._get_sessions = get_sessions
        self._get_invariants = get_invariants
        self._get_router = get_router
        self._get_lifecycle_lock = get_lifecycle_lock

    def generate(self, session_id: str) -> None:
        session = self._get_sessions().load(session_id)
        if session is None or session.title is not None or len(session.messages) < 2:
            return
        try:
            invariant_context = render_invariants_context(self._get_invariants().load())
        except (OSError, ValueError):
            return
        messages = self._title_messages(session, invariant_context)
        config = self._title_config(session)
        try:
            response = self._get_router().complete(messages, config)
        except ProviderError:
            return
        data = response.structured_data
        title = data.get("title") if isinstance(data, dict) else None
        if not isinstance(title, str):
            return
        normalized = " ".join(title.split())[:80]
        if not normalized:
            return
        with self._get_lifecycle_lock():
            latest = self._get_sessions().load(session_id)
            if latest is None or latest.title is not None:
                return
            latest.title = normalized
            latest.updated_at = datetime.now(UTC)
            self._get_sessions().save(latest)

    @staticmethod
    def _title_messages(session: ChatSession, invariant_context: str) -> list[ChatMessage]:
        source = session.messages[:2]
        title_request = ChatMessage(
            role="user",
            content=render_prompt(
                "copia.sessions",
                "title_request.md",
                user=source[0].content,
                assistant=source[1].content,
            ),
        )
        return LLMContextBuilder.build(invariants=invariant_context, history=[title_request])

    @staticmethod
    def _title_config(session: ChatSession) -> LLMConfig:
        return LLMConfig(
            provider=session.config.provider,
            model=session.config.model,
            generation=GenerationConfig(max_output_tokens=32, temperature=0),
            structured_output=StructuredOutputConfig(
                schema={
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                    "additionalProperties": False,
                },
                strict=True,
            ),
        )
