from __future__ import annotations

import json
import time

from copia.agent_logs.domain.services.agent_log_context import agent_log_operation
from copia.agents.domain.models.agent_config import AgentConfig
from copia.invariants.domain.models.invariant import Invariant
from copia.providers.application.llm_router import LLMRouter
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.provider_trace import ProviderTrace
from copia.providers.domain.models.structured_output_config import StructuredOutputConfig
from copia.security.domain.services.credential_sanitizer import sanitize_error
from copia.session_memory.domain.models.memory_candidate import MemoryCandidate
from copia.session_memory.domain.services.memory_classifier_prompt import (
    MEMORY_CLASSIFIER_SYSTEM_PROMPT,
)
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.services.context_strategy import render_invariants_context


class LLMMemoryClassifier:
    """Provider-agnostic structured classifier routed through the configured LLM."""

    def __init__(
        self,
        router: LLMRouter,
        config: AgentConfig,
        invariants: list[Invariant] | None = None,
    ) -> None:
        self._router = router
        self._config = config
        self._invariants = list(invariants or [])
        self.last_error: str | None = None
        self.last_trace: ProviderTrace | None = None
        self.last_duration_seconds: float | None = None
        self.last_request_body: dict = {}

    def set_invariants(self, invariants: list[Invariant]) -> None:
        self._invariants = list(invariants)

    def classify(self, message, transcript, working_memory, previous_assistant=None):
        self.last_error = None
        self.last_trace = None
        self.last_request_body = {}
        started_at = time.perf_counter()
        request_body: dict = {}
        stage = "request preparation"
        try:
            payload = {
                "message": message,
                "recent_transcript": [
                    item.model_dump(include={"role", "content"}) for item in transcript[-6:]
                ],
                "working_memory": [item.model_dump(mode="json") for item in working_memory],
                "previous_assistant": previous_assistant,
            }
            messages = [
                ChatMessage(
                    role="system",
                    content="\n\n".join(
                        part
                        for part in (
                            MEMORY_CLASSIFIER_SYSTEM_PROMPT,
                            render_invariants_context(self._invariants),
                        )
                        if part
                    ),
                ),
                ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
            ]
            config = LLMConfig(
                provider=self._config.provider,
                model=self._config.model,
                generation={"max_output_tokens": 512, "temperature": 0},
                structured_output=StructuredOutputConfig(
                    schema={
                        "type": "object",
                        "properties": {
                            "candidates": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "scope": {
                                            "type": "string",
                                            "enum": ["none", "working", "long_term"],
                                        },
                                        "action": {
                                            "type": "string",
                                            "enum": ["create", "update", "delete", "skip"],
                                        },
                                        "category": {
                                            "type": "string",
                                            "enum": ["profile", "decision", "knowledge"],
                                        },
                                        "key": {"type": "string"},
                                        "value": {"type": ["string", "null"]},
                                        "target_id": {"type": ["string", "null"]},
                                        "confidence": {"type": "number"},
                                        "reason": {"type": "string"},
                                    },
                                    "required": [
                                        "scope",
                                        "action",
                                        "category",
                                        "key",
                                        "value",
                                        "target_id",
                                        "confidence",
                                        "reason",
                                    ],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["candidates"],
                        "additionalProperties": False,
                    }
                ),
            )
            request_body = {
                "messages": [item.model_dump() for item in messages],
                "config": config.model_dump(mode="json"),
            }
            self.last_request_body = request_body
            stage = "provider request"
            with agent_log_operation(
                "memory_classification",
                provider=config.provider,
                model=config.model,
            ):
                response = self._router.complete(messages, config)
            self.last_trace = response.trace or ProviderTrace(
                status_code=200,
                request_body=request_body,
                response_body={
                    "content": response.content,
                    "structured_data": response.structured_data,
                },
            )
            self.last_duration_seconds = time.perf_counter() - started_at
            stage = "response validation"
            data = response.structured_data
            if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
                raise ValueError("invalid structured data")
            return [MemoryCandidate.model_validate(item) for item in data["candidates"]]
        except Exception as error:
            self.last_duration_seconds = time.perf_counter() - started_at
            request_body = getattr(error, "request_body", None) or request_body
            response_body = getattr(error, "response_body", None)
            status_code = getattr(error, "status_code", None)
            self.last_trace = ProviderTrace(
                status_code=status_code if isinstance(status_code, int) else 0,
                request_body=request_body,
                response_body=response_body
                if isinstance(response_body, dict)
                else {"error": str(error)},
            )
            details = sanitize_error(str(error) or type(error).__name__)
            self.last_error = sanitize_error(
                f"Memory classification failed at {stage}: "
                f"{type(error).__name__}: {details}; working memory was unchanged"
            )
            return []
