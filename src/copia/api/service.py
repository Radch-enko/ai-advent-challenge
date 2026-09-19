from __future__ import annotations

import base64
import os
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator

from ..data.agent_log_repository import JsonAgentLogRepository
from ..data.agent_log_store import AgentLogStore
from ..data.model_catalog import context_window_for
from ..data.path_identifiers import validate_path_identifier
from ..data.pending_memory_repository import PendingMemoryRepository
from ..data.profile_memory_repository import (
    ProfileMemoryLimitExceeded,
    ProfileMemoryRepository,
)
from ..data.profiles_repository import ProfilesRepository
from ..data.providers.llm import ProviderError
from ..data.sessions_repository import SessionsRepository
from ..data.user_profiles_repository import (
    JsonUserProfilesRepository,
    UserProfileNameConflictError,
    UserProfileStorageError,
)
from ..data.working_memory_repository import WorkingMemoryRepository
from ..domain.models.agent import (
    Agent,
    AgentFactory,
    FactsUpdateFailed,
    SummarizationFailed,
    SummarizationRetryRequired,
)
from ..domain.models.agent_log import AgentLogExchange, AgentLogOperation, AgentLogTurn
from ..domain.models.config import (
    AgentConfig,
    ChatMessage,
    CompletionConfig,
    ContextStrategyName,
    GenerationConfig,
    LLMConfig,
    LLMResponse,
    ProviderCapabilities,
    ProviderModel,
    ProviderName,
    ProviderTrace,
    StructuredOutputConfig,
)
from ..domain.models.memory import (
    LongTermMemoryCreate,
    LongTermMemoryItem,
    LongTermMemoryUpdate,
    MemoryEvent,
    PendingMemorySuggestion,
    WorkingMemoryItem,
)
from ..domain.models.session import (
    ChatSession,
    ChatSessionSummary,
    FactsUpdateEvent,
    SummarizationEvent,
)
from ..domain.models.user_profile import UserProfile, UserProfileCreate, UserProfileUpdate
from ..domain.services.agent_log_context import agent_log_operation, agent_log_turn
from ..domain.services.context_strategy import _render_user_profile_block
from ..domain.services.credential_sanitizer import sanitize_error, sanitize_text, sanitize_value
from ..domain.services.memory_classifier import LLMMemoryClassifier
from ..domain.services.router import LLMRouter

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
profiles_path = Path(os.getenv("COPIA_PROFILES_PATH", PROJECT_ROOT / "profiles.json"))
sessions_path = Path(os.getenv("COPIA_SESSIONS_PATH", "~/.copia/sessions"))
agent_log_store = AgentLogStore(repository=JsonAgentLogRepository(sessions_path))
router = LLMRouter(agent_log_store=agent_log_store)
factory = AgentFactory(router, ProfilesRepository(profiles_path))
agents: dict[str, Agent] = {}
sessions = SessionsRepository(sessions_path)
profile_memory = ProfileMemoryRepository(Path(os.getenv("COPIA_MEMORY_PATH", "~/.copia/memory")))
working_memory = WorkingMemoryRepository(sessions_path)
pending_memory: dict[str, list[PendingMemorySuggestion]] = {}
pending_memory_repository = PendingMemoryRepository(sessions_path)
user_profiles = JsonUserProfilesRepository()
session_lifecycle_lock = threading.RLock()


@dataclass
class _SessionLockState:
    session_id: str
    lock: threading.Lock
    users: int = 0
    retired: bool = False


session_message_locks: dict[str, _SessionLockState] = {}
MAX_APPROVED_MEMORY_MUTATIONS = 1024
approved_memory_mutations: OrderedDict[tuple[str, str], LongTermMemoryMutationResponse] = (
    OrderedDict()
)

app = FastAPI(title="Copia API", version="0.1.0")


def provider_error_detail(
    error: ProviderError, *, redact_request: bool = False
) -> dict[str, object]:
    return {
        "message": "Provider request failed",
        "provider_trace": {
            "status_code": error.status_code,
            "request_body": sanitize_value(error.request_body),
            "response_body": sanitize_value(error.response_body),
        },
    }


class CreateAgentRequest(BaseModel):
    profile_name: str | None = None
    config: AgentConfig | None = None
    long_term_memory_enabled: bool = False

    @model_validator(mode="after")
    def require_one_source(self) -> CreateAgentRequest:
        if self.profile_name is not None:
            validate_path_identifier(self.profile_name, "profile name")
        if (self.profile_name is None) == (self.config is None):
            raise ValueError("Provide exactly one of profile_name or config")
        if self.long_term_memory_enabled and self.profile_name is None:
            raise ValueError("Long-term memory is available only for profile agents")
        return self


class CreateAgentResponse(BaseModel):
    agent_id: str
    config: AgentConfig
    long_term_memory_enabled: bool


class MessageRequest(BaseModel):
    content: str = Field(min_length=1)
    config: AgentConfig | None = None


class ContextManagementUpdate(BaseModel):
    enabled: bool | None = None
    strategy: ContextStrategyName | None = None
    recent_message_limit: int | None = Field(default=None, ge=1)


class LongTermMemoryToggleUpdate(BaseModel):
    enabled: bool


class MessageResponse(BaseModel):
    response: LLMResponse
    summarization_events: list[SummarizationEvent] = Field(default_factory=list)
    facts_events: list[FactsUpdateEvent] = Field(default_factory=list)
    facts: dict[str, str] = Field(default_factory=dict)
    memory_events: list[MemoryEvent] = Field(default_factory=list)
    pending_memory: list[PendingMemorySuggestion] = Field(default_factory=list)
    working_memory: list[WorkingMemoryItem] = Field(default_factory=list)


class SessionLLMResponse(BaseModel):
    """Session response data without the legacy synthetic provider trace."""

    content: str
    provider: ProviderName
    model: str
    usage: dict[str, int] | None = None
    context_window: int | None = None
    structured_data: dict[str, object] | list[object] | None = None
    # Preserve the session response shape without serializing provider data.
    trace: None = None

    @classmethod
    def from_response(cls, response: LLMResponse) -> SessionLLMResponse:
        return cls(
            content=response.content,
            provider=response.provider,
            model=response.model,
            usage=response.usage,
            context_window=response.context_window,
            structured_data=response.structured_data,
        )


class SessionMessageResponse(BaseModel):
    response: SessionLLMResponse
    agent_log_id: str
    summarization_events: list[SummarizationEvent] = Field(default_factory=list)
    facts_events: list[FactsUpdateEvent] = Field(default_factory=list)
    facts: dict[str, str] = Field(default_factory=dict)
    memory_events: list[MemoryEvent] = Field(default_factory=list)
    pending_memory: list[PendingMemorySuggestion] = Field(default_factory=list)
    working_memory: list[WorkingMemoryItem] = Field(default_factory=list)


class AgentLogBodyResponse(BaseModel):
    content: str
    encoding: Literal["utf-8", "base64"]
    size_bytes: int
    truncated: bool = False


class AgentLogExchangeResponse(BaseModel):
    id: str
    agent_turn_id: str
    operation: str
    provider: ProviderName | None = None
    model: str | None = None
    method: str
    url: str
    request_headers: dict[str, str]
    request_body: AgentLogBodyResponse | None = None
    status_code: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: AgentLogBodyResponse | None = None
    duration_seconds: float
    error: str | None = None
    created_at: datetime


class AgentLogResponse(BaseModel):
    agent_log_id: str
    agent_turn_id: str
    session_id: str
    status: Literal["running", "completed", "failed"]
    provider: ProviderName | None = None
    model: str | None = None
    usage: dict[str, int] | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float
    error: str | None = None
    operations: list[AgentLogOperation] = Field(default_factory=list)
    exchanges: list[AgentLogExchangeResponse] = Field(default_factory=list)


AgentLogDetail = AgentLogResponse


class LongTermMemoryMutationResponse(LongTermMemoryItem):
    memory_events: list[MemoryEvent] = Field(default_factory=list)


class WorkingMemoryMutationResponse(WorkingMemoryItem):
    memory_events: list[MemoryEvent] = Field(default_factory=list)


class WorkingMemoryCollectionResponse(BaseModel):
    working_memory: list[WorkingMemoryItem] = Field(default_factory=list)
    memory_events: list[MemoryEvent] = Field(default_factory=list)


def _session_message_response(
    response: LLMResponse,
    agent_log_id: str,
    *,
    summarization_events: list[SummarizationEvent] | None = None,
    facts_events: list[FactsUpdateEvent] | None = None,
    facts: dict[str, str] | None = None,
    memory_events: list[MemoryEvent] | None = None,
    pending_memory: list[PendingMemorySuggestion] | None = None,
    working_memory: list[WorkingMemoryItem] | None = None,
) -> SessionMessageResponse:
    return SessionMessageResponse(
        response=SessionLLMResponse.from_response(response),
        agent_log_id=agent_log_id,
        summarization_events=_safe_summarization_events(summarization_events or []),
        facts_events=_safe_facts_events(facts_events or []),
        facts=facts or {},
        memory_events=_safe_memory_events(memory_events or []),
        pending_memory=pending_memory or [],
        working_memory=working_memory or [],
    )


def _agent_log_response(turn: AgentLogTurn) -> AgentLogResponse:
    return AgentLogResponse(
        agent_log_id=turn.agent_turn_id,
        agent_turn_id=turn.agent_turn_id,
        session_id=turn.session_id,
        status=turn.status,
        provider=turn.provider,
        model=turn.model,
        usage=turn.usage,
        started_at=turn.started_at,
        completed_at=turn.completed_at,
        duration_seconds=turn.duration_seconds,
        error=turn.error,
        operations=turn.operations,
        exchanges=[_agent_log_exchange_response(exchange) for exchange in turn.exchanges],
    )


def _agent_log_exchange_response(exchange: AgentLogExchange) -> AgentLogExchangeResponse:
    return AgentLogExchangeResponse(
        id=exchange.id,
        agent_turn_id=exchange.agent_turn_id,
        operation=exchange.operation,
        provider=exchange.provider,
        model=exchange.model,
        method=exchange.method,
        url=exchange.url,
        request_headers=exchange.request_headers,
        request_body=_agent_log_body(exchange.request_body, exchange.request_body_truncated),
        status_code=exchange.status_code,
        response_headers=exchange.response_headers,
        response_body=_agent_log_body(exchange.response_body, exchange.response_body_truncated),
        duration_seconds=exchange.duration_seconds,
        error=exchange.error,
        created_at=exchange.created_at,
    )


def _agent_log_body(body: bytes | None, truncated: bool) -> AgentLogBodyResponse | None:
    if body is None:
        return None
    try:
        content = body.decode("utf-8")
        encoding: Literal["utf-8", "base64"] = "utf-8"
    except UnicodeDecodeError:
        content = base64.b64encode(body).decode("ascii")
        encoding = "base64"
    return AgentLogBodyResponse(
        content=content,
        encoding=encoding,
        size_bytes=len(body),
        truncated=truncated,
    )


def _safe_trace(trace: ProviderTrace | None) -> ProviderTrace | None:
    if trace is None:
        return None
    return ProviderTrace(
        status_code=trace.status_code,
        request_body=sanitize_value(trace.request_body),
        response_body=sanitize_value(trace.response_body),
    )


def _safe_summarization_events(events: list[SummarizationEvent]) -> list[SummarizationEvent]:
    return [
        event.model_copy(
            deep=True,
            update={"trace": _safe_trace(event.trace), "error": _safe_error_text(event.error)},
        )
        for event in events
    ]


def _safe_facts_events(events: list[FactsUpdateEvent]) -> list[FactsUpdateEvent]:
    return [
        event.model_copy(
            deep=True,
            update={"trace": _safe_trace(event.trace), "error": _safe_error_text(event.error)},
        )
        for event in events
    ]


def _safe_memory_events(events: list[MemoryEvent]) -> list[MemoryEvent]:
    return [
        event.model_copy(
            deep=True,
            update={"trace": _safe_trace(event.trace), "message": _safe_error_text(event.message)},
        )
        for event in events
    ]


def _safe_error_text(value: str | None) -> str | None:
    if value is None:
        return None
    return sanitize_error(value)


def _session_failure_trace(error: ProviderError) -> ProviderTrace:
    return ProviderTrace(
        status_code=error.status_code,
        request_body=sanitize_value(error.request_body),
        response_body=sanitize_value(
            error.response_body
            if isinstance(error.response_body, dict)
            else {"raw": error.response_body}
        ),
    )


class CompletionRequest(BaseModel):
    config: CompletionConfig
    messages: list[ChatMessage] = Field(min_length=1)


class CreateSessionRequest(BaseModel):
    profile_name: str | None = None
    config: AgentConfig | None = None
    user_profile_id: str | None = None

    @model_validator(mode="after")
    def require_one_source(self) -> CreateSessionRequest:
        if self.profile_name is not None:
            validate_path_identifier(self.profile_name, "profile name")
        if (self.profile_name is None) == (self.config is None):
            raise ValueError("Provide exactly one of profile_name or config")
        return self


class UserProfileSelectionUpdate(BaseModel):
    user_profile_id: str | None = None


class ForkSessionRequest(BaseModel):
    message_index: int = Field(ge=0)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/profiles")
def profiles() -> dict[str, AgentConfig]:
    return factory.profiles()


async def _require_profile(profile_name: str) -> None:
    try:
        validate_path_identifier(profile_name, "profile name")
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid profile name") from error
    try:
        profiles = await run_in_threadpool(factory.profiles)
    except (OSError, ValueError) as error:
        raise _memory_storage_error() from error
    if profile_name not in profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown profile: {profile_name}"
        )


@app.get("/profiles/{profile_name}/memory", response_model=list[LongTermMemoryItem])
async def list_profile_memory(profile_name: str) -> list[LongTermMemoryItem]:
    await _require_profile(profile_name)
    try:
        return await run_in_threadpool(profile_memory.load, profile_name)
    except (OSError, ValueError) as error:
        raise _memory_storage_error() from error


@app.post(
    "/profiles/{profile_name}/memory",
    response_model=LongTermMemoryItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile_memory(
    profile_name: str, request: LongTermMemoryCreate
) -> LongTermMemoryItem:
    await _require_profile(profile_name)
    try:
        return await run_in_threadpool(_create_profile_memory, profile_name, request)
    except ProfileMemoryLimitExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Profile memory limit reached"
        ) from error
    except (OSError, ValueError) as error:
        raise _memory_storage_error() from error


def _create_profile_memory(profile_name: str, request: LongTermMemoryCreate) -> LongTermMemoryItem:
    now = datetime.now(UTC)
    item = LongTermMemoryItem(
        id=str(uuid.uuid4()), **request.model_dump(), created_at=now, updated_at=now
    )
    return profile_memory.create(profile_name, item)


@app.patch("/profiles/{profile_name}/memory/{item_id}", response_model=LongTermMemoryItem)
async def update_profile_memory(
    profile_name: str, item_id: str, request: LongTermMemoryUpdate
) -> LongTermMemoryItem:
    await _require_profile(profile_name)
    try:
        changes = request.model_dump(exclude_none=True)
        changes["updated_at"] = datetime.now(UTC)
        return await run_in_threadpool(profile_memory.update, profile_name, item_id, changes)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown memory item"
        ) from error
    except (OSError, ValueError) as error:
        raise _memory_storage_error() from error


@app.delete("/profiles/{profile_name}/memory/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile_memory(profile_name: str, item_id: str) -> None:
    await _require_profile(profile_name)
    try:
        await run_in_threadpool(profile_memory.delete_item, profile_name, item_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown memory item"
        ) from error
    except (OSError, ValueError) as error:
        raise _memory_storage_error() from error


def _memory_storage_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Long-term memory storage is unavailable",
    )


def _session_initialization_error(
    agent_log_id: str,
    message: str,
    code: str,
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
) -> HTTPException:
    _finish_agent_log(agent_log_id, status="failed", error=message)
    return HTTPException(
        status_code=status_code,
        detail={"message": message, "code": code, "agent_log_id": agent_log_id},
    )


async def _load_user_profile_for_turn(
    session: ChatSession, agent_log_id: str
) -> UserProfile | None:
    started = time.perf_counter()
    if session.user_profile_id is None:
        agent_log_store.append_operation(
            AgentLogOperation(
                id=str(uuid.uuid4()),
                agent_turn_id=agent_log_id,
                session_id=session.id,
                operation="user_profile_load",
                status="skipped",
                preference_count=0,
                applied=False,
                duration_seconds=time.perf_counter() - started,
                created_at=datetime.now(UTC),
            )
        )
        return None
    try:
        profile = await run_in_threadpool(user_profiles.get, session.user_profile_id)
        if profile is None:
            raise UserProfileStorageError("User profile was not found")
        # Validate the rendered, escaped prompt before recording the operation
        # as applied. This also protects against legacy storage bypassing API
        # model validation.
        _render_user_profile_block(profile)
    except (UserProfileStorageError, OSError, ValueError) as error:
        agent_log_store.append_operation(
            AgentLogOperation(
                id=str(uuid.uuid4()),
                agent_turn_id=agent_log_id,
                session_id=session.id,
                operation="user_profile_load",
                status="failed",
                profile_id=session.user_profile_id,
                preference_count=0,
                applied=False,
                duration_seconds=time.perf_counter() - started,
                error_code="user_profile_unavailable",
                message="User profile could not be loaded",
                created_at=datetime.now(UTC),
            )
        )
        raise _session_initialization_error(
            agent_log_id, "User profile is unavailable", "user_profile_unavailable", 409
        ) from error
    agent_log_store.append_operation(
        AgentLogOperation(
            id=str(uuid.uuid4()),
            agent_turn_id=agent_log_id,
            session_id=session.id,
            operation="user_profile_load",
            status="completed",
            profile_id=profile.id,
            profile_name=sanitize_text(profile.name),
            preference_count=5,
            applied=True,
            duration_seconds=time.perf_counter() - started,
            created_at=datetime.now(UTC),
        )
    )
    return profile


def _cache_approved_memory_mutation(
    key: tuple[str, str], result: LongTermMemoryMutationResponse
) -> None:
    approved_memory_mutations[key] = result
    approved_memory_mutations.move_to_end(key)
    while len(approved_memory_mutations) > MAX_APPROVED_MEMORY_MUTATIONS:
        approved_memory_mutations.popitem(last=False)


@app.get("/providers/{provider_name}/capabilities")
def capabilities(provider_name: ProviderName) -> ProviderCapabilities:
    try:
        return router.capabilities(provider_name)
    except ProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider is unavailable"
        ) from error


@app.get("/providers/{provider_name}/models", response_model=list[ProviderModel])
async def models(provider_name: ProviderName) -> list[ProviderModel]:
    try:
        return await run_in_threadpool(router.models, provider_name)
    except ProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=provider_error_detail(error)
        ) from error


@app.post("/completions", response_model=MessageResponse)
async def completion(request: CompletionRequest) -> MessageResponse:
    messages = list(request.messages)
    if request.config.system_prompt:
        messages.insert(0, ChatMessage(role="system", content=request.config.system_prompt))
    try:
        response = await run_in_threadpool(router.complete, messages, request.config)
    except ProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=provider_error_detail(error)
        ) from error
    return MessageResponse(response=response)


@app.post("/agents", response_model=CreateAgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(request: CreateAgentRequest) -> CreateAgentResponse:
    try:
        if request.profile_name is not None:
            agent = factory.create_from_profile(request.profile_name)
            agent = Agent(
                config=agent.config,
                router=router,
                long_term_memory_loader=(
                    (lambda: profile_memory.load(request.profile_name))
                    if request.long_term_memory_enabled
                    else None
                ),
                context_window=context_window_for(agent.config.provider, agent.config.model),
            )
        else:
            agent = factory.create(request.config)  # type: ignore[arg-type]
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (OSError, ValueError) as error:
        raise _memory_storage_error() from error

    agent_id = str(uuid.uuid4())
    agents[agent_id] = agent
    return CreateAgentResponse(
        agent_id=agent_id,
        config=agent.config,
        long_term_memory_enabled=request.long_term_memory_enabled,
    )


@app.post("/agents/{agent_id}/messages", response_model=MessageResponse)
async def send_message(agent_id: str, request: MessageRequest) -> MessageResponse:
    agent = agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
    try:
        response = await run_in_threadpool(agent.ask, request.content)
    except ProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=provider_error_detail(error, redact_request=agent.has_long_term_memory),
        ) from error
    except (OSError, ValueError) as error:
        raise _memory_storage_error() from error
    return MessageResponse(response=response, memory_events=agent.memory_events)


@app.get("/sessions", response_model=list[ChatSessionSummary])
def list_sessions() -> list[ChatSessionSummary]:
    return sessions.list()


def _user_profile_error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _sorted_user_profiles() -> list[UserProfile]:
    return sorted(user_profiles.list(), key=lambda profile: (profile.name.casefold(), profile.id))


@app.get("/user-profiles", response_model=list[UserProfile])
async def list_user_profiles() -> list[UserProfile]:
    try:
        return await run_in_threadpool(_sorted_user_profiles)
    except UserProfileStorageError as error:
        raise _user_profile_error(
            "user_profile_unavailable", "User profiles are unavailable", 500
        ) from error


@app.post("/user-profiles", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
async def create_user_profile(request: UserProfileCreate) -> UserProfile:
    def create() -> UserProfile:
        now = datetime.now(UTC)
        return user_profiles.create(
            UserProfile(
                id=str(uuid.uuid4()), **request.model_dump(), created_at=now, updated_at=now
            )
        )

    try:
        return await run_in_threadpool(create)
    except UserProfileNameConflictError as error:
        raise _user_profile_error(
            "user_profile_name_conflict", "A user profile with this name already exists", 409
        ) from error
    except UserProfileStorageError as error:
        raise _user_profile_error(
            "user_profile_unavailable", "User profiles are unavailable", 500
        ) from error


@app.patch("/user-profiles/{profile_id}", response_model=UserProfile)
async def update_user_profile(profile_id: str, request: UserProfileUpdate) -> UserProfile:
    def update() -> UserProfile:
        current = user_profiles.get(profile_id)
        if current is None:
            raise _user_profile_error("user_profile_not_found", "User profile was not found", 404)
        changes = request.model_dump(exclude_none=True)
        changes["updated_at"] = datetime.now(UTC)
        return user_profiles.update(profile_id, changes)

    try:
        return await run_in_threadpool(update)
    except UserProfileNameConflictError as error:
        raise _user_profile_error(
            "user_profile_name_conflict", "A user profile with this name already exists", 409
        ) from error
    except UserProfileStorageError as error:
        raise _user_profile_error(
            "user_profile_unavailable", "User profiles are unavailable", 500
        ) from error


@app.delete("/user-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_profile(profile_id: str) -> None:
    def delete() -> None:
        if user_profiles.get(profile_id) is None:
            raise _user_profile_error("user_profile_not_found", "User profile was not found", 404)
        if any(
            (session := sessions.load(summary.id)) is not None
            and session.user_profile_id == profile_id
            for summary in sessions.list()
        ):
            raise _user_profile_error(
                "user_profile_in_use", "User profile is used by a session", 409
            )
        user_profiles.delete(profile_id)

    try:
        await run_in_threadpool(delete)
    except UserProfileStorageError as error:
        raise _user_profile_error(
            "user_profile_unavailable", "User profiles are unavailable", 500
        ) from error


@app.post("/sessions", response_model=ChatSession, status_code=status.HTTP_201_CREATED)
def create_session(request: CreateSessionRequest) -> ChatSession:
    try:
        config = (
            factory.profiles()[request.profile_name]
            if request.profile_name is not None
            else request.config
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown profile: {request.profile_name}"
        ) from error
    try:
        if (
            request.user_profile_id is not None
            and user_profiles.get(request.user_profile_id) is None
        ):
            raise _user_profile_error("user_profile_not_found", "User profile was not found", 404)
    except UserProfileStorageError as error:
        raise _user_profile_error(
            "user_profile_unavailable", "User profiles are unavailable", 500
        ) from error
    assert config is not None
    now = datetime.now(UTC)
    session = ChatSession(
        id=str(uuid.uuid4()),
        config=config,
        profile_name=request.profile_name,
        user_profile_id=request.user_profile_id,
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)
    return session


@app.get("/sessions/{session_id}", response_model=ChatSession)
def get_session(session_id: str) -> ChatSession:
    try:
        validate_path_identifier(session_id, "session ID")
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid session ID") from error
    session = sessions.load(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
    return session


def _get_session_locked(session_id: str) -> ChatSession:
    try:
        validate_path_identifier(session_id, "session ID")
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid session ID") from error
    session = sessions.load(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
    return session


async def _get_session(session_id: str) -> ChatSession:
    try:
        validate_path_identifier(session_id, "session ID")
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid session ID") from error
    session = await run_in_threadpool(sessions.load, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
    return session


def _session_message_lock(session_id: str) -> _SessionLockState:
    try:
        validate_path_identifier(session_id, "session ID")
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid session ID") from error
    with session_lifecycle_lock:
        existing = session_message_locks.get(session_id)
        if isinstance(existing, _SessionLockState):
            state = existing
        else:
            state = _SessionLockState(session_id=session_id, lock=existing or threading.Lock())
            session_message_locks[session_id] = state
        state.users += 1
        return state


def _release_session_message_lock(state: _SessionLockState) -> None:
    with session_lifecycle_lock:
        state.users -= 1
        if state.retired and state.users == 0:
            session_message_locks.pop(state.session_id, None)


@contextmanager
def _session_mutation_lock(session_id: str):
    """Keep UI memory mutations ordered with the send/retry read-save cycle."""
    message_lock = _session_message_lock(session_id)
    message_lock.lock.acquire()
    try:
        with session_lifecycle_lock:
            yield
    finally:
        message_lock.lock.release()
        _release_session_message_lock(message_lock)


@app.get("/sessions/{session_id}/facts", response_model=dict[str, str])
async def get_session_facts(session_id: str) -> dict[str, str]:
    await _get_session(session_id)
    try:
        return await run_in_threadpool(sessions.load_facts, session_id)
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session facts are unavailable",
        ) from error


@app.patch("/sessions/{session_id}/context-management", response_model=ChatSession)
def update_session_context_management(
    session_id: str, request: ContextManagementUpdate
) -> ChatSession:
    message_lock = _session_message_lock(session_id)
    message_lock.lock.acquire()
    try:
        with session_lifecycle_lock:
            session = _get_session_locked(session_id)
            if request.enabled is not None:
                session.config.context_management.enabled = request.enabled
            if request.strategy is not None:
                session.config.context_management.strategy = request.strategy
            if request.recent_message_limit is not None:
                session.config.context_management.recent_message_limit = (
                    request.recent_message_limit
                )
            session.updated_at = datetime.now(UTC)
            sessions.save(session)
            return session
    finally:
        message_lock.lock.release()
        _release_session_message_lock(message_lock)


@app.patch("/sessions/{session_id}/user-profile", response_model=ChatSession)
async def update_session_user_profile(
    session_id: str, request: UserProfileSelectionUpdate
) -> ChatSession:
    def update() -> ChatSession:
        message_lock = _session_message_lock(session_id)
        message_lock.lock.acquire()
        try:
            with session_lifecycle_lock:
                session = _get_session_locked(session_id)
                if (
                    request.user_profile_id is not None
                    and user_profiles.get(request.user_profile_id) is None
                ):
                    raise _user_profile_error(
                        "user_profile_not_found", "User profile was not found", 404
                    )
                session.user_profile_id = request.user_profile_id
                session.updated_at = datetime.now(UTC)
                sessions.save(session)
                return session
        finally:
            message_lock.lock.release()
            _release_session_message_lock(message_lock)

    try:
        return await run_in_threadpool(update)
    except UserProfileStorageError as error:
        raise _user_profile_error(
            "user_profile_unavailable", "User profiles are unavailable", 500
        ) from error


@app.patch("/sessions/{session_id}/long-term-memory", response_model=ChatSession)
async def update_session_long_term_memory(
    session_id: str, request: LongTermMemoryToggleUpdate
) -> ChatSession:
    return await run_in_threadpool(_update_session_long_term_memory, session_id, request)


def _update_session_long_term_memory(
    session_id: str, request: LongTermMemoryToggleUpdate
) -> ChatSession:
    # Keep the lock order identical to send/retry and delete: message lock first,
    # then lifecycle lock. This makes the toggle wait for an in-flight send before
    # changing the state that the send will persist.
    message_lock = _session_message_lock(session_id)
    message_lock.lock.acquire()
    try:
        with session_lifecycle_lock:
            session = _get_session_locked(session_id)
            if session.profile_name is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Long-term memory is unavailable without a profile",
                )
            session.long_term_memory_enabled = request.enabled
            session.updated_at = datetime.now(UTC)
            sessions.save(session)
            return session
    finally:
        message_lock.lock.release()
        _release_session_message_lock(message_lock)


@app.post(
    "/sessions/{session_id}/fork", response_model=ChatSession, status_code=status.HTTP_201_CREATED
)
def fork_session(session_id: str, request: ForkSessionRequest) -> ChatSession:
    with session_lifecycle_lock:
        source = _get_session_locked(session_id)
        if source.config.context_management.strategy != ContextStrategyName.BRANCHING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Forking requires the branching strategy",
            )
        if request.message_index >= len(source.messages):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Message index is outside the transcript",
            )

        now = datetime.now(UTC)
        fork = ChatSession(
            id=str(uuid.uuid4()),
            config=source.config.model_copy(deep=True),
            messages=[
                message.model_copy(update={"agent_log_id": None})
                for message in source.messages[: request.message_index + 1]
            ],
            title=f"{source.title or 'Новый чат'} · ветка",
            profile_name=source.profile_name,
            user_profile_id=source.user_profile_id,
            long_term_memory_enabled=source.long_term_memory_enabled,
            created_at=now,
            updated_at=now,
        )
        sessions.save(fork)
        return fork


@app.post("/sessions/{session_id}/messages", response_model=SessionMessageResponse)
async def send_session_message(
    session_id: str, request: MessageRequest, background_tasks: BackgroundTasks
) -> SessionMessageResponse:
    # Acquire outside the event loop: another request for this session may be in provider I/O.
    message_lock = _session_message_lock(session_id)
    await run_in_threadpool(message_lock.lock.acquire)
    try:
        return await _send_session_message_locked(session_id, request, background_tasks)
    finally:
        message_lock.lock.release()
        _release_session_message_lock(message_lock)


async def _send_session_message_locked(
    session_id: str, request: MessageRequest, background_tasks: BackgroundTasks
) -> SessionMessageResponse:
    try:
        session = await _get_session(session_id)
    except (OSError, ValueError) as error:
        validate_path_identifier(session_id, "session ID")
        agent_log_id = agent_log_store.start_turn(session_id)
        raise _session_initialization_error(
            agent_log_id, "Session is unavailable", "session_unavailable"
        ) from error
    agent_log_id = agent_log_store.start_turn(session.id)
    if request.config is not None and session.profile_name is None:
        session.config = request.config
    user_profile = await _load_user_profile_for_turn(session, agent_log_id)
    try:
        facts = await run_in_threadpool(sessions.load_facts, session.id)
    except (OSError, ValueError) as error:
        raise _session_initialization_error(
            agent_log_id, "Session facts are unavailable", "session_facts_unavailable"
        ) from error
    try:
        long_term_memory = await run_in_threadpool(_long_term_memory_for_session, session, facts)
    except (OSError, ValueError) as error:
        raise _session_initialization_error(
            agent_log_id, "Long-term memory is unavailable", "long_term_memory_unavailable"
        ) from error
    try:
        loaded_working_memory = await run_in_threadpool(working_memory.load, session.id)
    except (OSError, ValueError) as error:
        raise _session_initialization_error(
            agent_log_id, "Working memory is unavailable", "working_memory_unavailable"
        ) from error
    try:
        loaded_pending_memory = await run_in_threadpool(pending_memory_repository.load, session.id)
    except (OSError, ValueError) as error:
        raise _session_initialization_error(
            agent_log_id, "Pending memory is unavailable", "pending_memory_unavailable"
        ) from error
    try:
        agent = Agent(
            config=session.config,
            router=router,
            history=session.messages,
            context=session.context,
            facts=facts,
            long_term_memory=long_term_memory,
            context_window=context_window_for(session.config.provider, session.config.model),
            working_memory=loaded_working_memory,
            working_memory_store=working_memory,
            session_id=session.id,
            memory_classifier=LLMMemoryClassifier(router, session.config),
            pending_memory=loaded_pending_memory,
            user_profile=user_profile,
        )
    except (OSError, TypeError, ValueError) as error:
        raise _session_initialization_error(
            agent_log_id, "Agent initialization failed", "agent_initialization_failed"
        ) from error
    try:
        response = await run_in_threadpool(
            _ask_agent, session.id, agent, request.content, agent_log_id, True
        )
    except FactsUpdateFailed as error:
        _save_agent_state(session, agent)
        _finish_agent_log(
            agent_log_id,
            provider=error.event.provider,
            model=error.event.model,
            status="failed",
            error="Facts update failed",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Facts update failed",
                "code": "facts_update_failed",
                "agent_log_id": agent_log_id,
                "facts_event": _safe_facts_events([error.event])[0].model_dump(mode="json"),
            },
        ) from error
    except SummarizationFailed as error:
        _save_agent_state(session, agent)
        _finish_agent_log(
            agent_log_id,
            provider=error.event.provider,
            model=error.event.model,
            status="failed",
            error="Conversation summarization failed",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Conversation summarization failed",
                "code": "summarization_failed",
                "agent_log_id": agent_log_id,
                "summarization_event": _safe_summarization_events([error.event])[0].model_dump(
                    mode="json"
                ),
            },
        ) from error
    except SummarizationRetryRequired as error:
        _finish_agent_log(agent_log_id, status="failed", error="Summarization retry required")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Summarization retry required",
                "code": "summarization_retry_required",
                "agent_log_id": agent_log_id,
            },
        ) from error
    except ProviderError as error:
        _save_agent_state(session, agent)
        _finish_agent_log(
            agent_log_id,
            provider=session.config.provider,
            model=session.config.model,
            status="failed",
            error="Provider request failed",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Provider request failed",
                "code": "provider_request_failed",
                "agent_log_id": agent_log_id,
                "provider_trace": _session_failure_trace(error).model_dump(mode="json"),
            },
        ) from error

    _save_agent_state(session, agent)
    _finish_agent_log(
        agent_log_id,
        provider=response.provider,
        model=response.model,
        usage=response.usage,
        status="completed",
    )
    if session.title is None:
        background_tasks.add_task(generate_session_title, session.id, agent_log_id)
    return _session_message_response(
        response,
        agent_log_id,
        summarization_events=agent.operation_events,
        facts_events=agent.facts_operation_events,
        facts=agent.facts,
        memory_events=agent.memory_events,
        pending_memory=agent.pending_memory,
        working_memory=agent.working_memory,
    )


@app.get("/sessions/{session_id}/agent-logs/{agent_log_id}", response_model=AgentLogResponse)
async def get_agent_log(session_id: str, agent_log_id: str) -> AgentLogResponse:
    await _get_session(session_id)
    try:
        validate_path_identifier(agent_log_id, "agent log ID")
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid agent log ID") from error
    turn = await run_in_threadpool(agent_log_store.get_turn, session_id, agent_log_id)
    if turn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent log is unavailable"
        )
    return _agent_log_response(turn)


@app.post("/sessions/{session_id}/summarization/retry", response_model=SessionMessageResponse)
async def retry_session_summarization(session_id: str) -> SessionMessageResponse:
    # Serialize the complete read -> retry -> save flow with send_session_message.
    message_lock = _session_message_lock(session_id)
    await run_in_threadpool(message_lock.lock.acquire)
    try:
        try:
            session = await _get_session(session_id)
        except (OSError, ValueError) as error:
            validate_path_identifier(session_id, "session ID")
            agent_log_id = agent_log_store.start_turn(session_id)
            raise _session_initialization_error(
                agent_log_id, "Session is unavailable", "session_unavailable"
            ) from error
        agent_log_id = agent_log_store.start_turn(session.id)
        user_profile = await _load_user_profile_for_turn(session, agent_log_id)
        try:
            facts = await run_in_threadpool(sessions.load_facts, session.id)
            long_term_memory = await run_in_threadpool(
                _long_term_memory_for_session, session, facts
            )
        except (OSError, ValueError) as error:
            raise _session_initialization_error(
                agent_log_id, "Session memory is unavailable", "session_memory_unavailable"
            ) from error
        try:
            loaded_working_memory = await run_in_threadpool(working_memory.load, session.id)
            loaded_pending_memory = await run_in_threadpool(
                pending_memory_repository.load, session.id
            )
        except (OSError, ValueError) as error:
            raise _session_initialization_error(
                agent_log_id, "Session memory is unavailable", "session_memory_unavailable"
            ) from error
        try:
            agent = Agent(
                config=session.config,
                router=router,
                history=session.messages,
                context=session.context,
                facts=facts,
                long_term_memory=long_term_memory,
                context_window=context_window_for(session.config.provider, session.config.model),
                working_memory=loaded_working_memory,
                working_memory_store=working_memory,
                session_id=session.id,
                memory_classifier=LLMMemoryClassifier(router, session.config),
                pending_memory=loaded_pending_memory,
                user_profile=user_profile,
            )
        except (OSError, TypeError, ValueError) as error:
            raise _session_initialization_error(
                agent_log_id, "Agent initialization failed", "agent_initialization_failed"
            ) from error
        try:
            response = await run_in_threadpool(_retry_agent, session.id, agent, agent_log_id, True)
        except SummarizationFailed as error:
            _save_agent_state(session, agent)
            _finish_agent_log(
                agent_log_id,
                provider=error.event.provider,
                model=error.event.model,
                status="failed",
                error="Conversation summarization failed",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Conversation summarization failed",
                    "code": "summarization_failed",
                    "agent_log_id": agent_log_id,
                    "summarization_event": _safe_summarization_events([error.event])[0].model_dump(
                        mode="json"
                    ),
                },
            ) from error
        except SummarizationRetryRequired as error:
            _finish_agent_log(agent_log_id, status="failed", error="Summarization retry required")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Summarization retry required",
                    "code": "summarization_retry_required",
                    "agent_log_id": agent_log_id,
                },
            ) from error
        except ProviderError as error:
            _save_agent_state(session, agent)
            _finish_agent_log(
                agent_log_id,
                provider=session.config.provider,
                model=session.config.model,
                status="failed",
                error="Provider request failed",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Provider request failed",
                    "code": "provider_request_failed",
                    "agent_log_id": agent_log_id,
                    "provider_trace": _session_failure_trace(error).model_dump(mode="json"),
                },
            ) from error

        _save_agent_state(session, agent)
        _finish_agent_log(
            agent_log_id,
            provider=response.provider,
            model=response.model,
            usage=response.usage,
            status="completed",
        )
        return _session_message_response(
            response,
            agent_log_id,
            summarization_events=agent.operation_events,
            facts_events=agent.facts_operation_events,
            facts=agent.facts,
            memory_events=agent.memory_events,
            pending_memory=agent.pending_memory,
            working_memory=agent.working_memory,
        )
    finally:
        message_lock.lock.release()
        _release_session_message_lock(message_lock)


@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str) -> None:
    # Acquire the per-session lock before the lifecycle lock so deletion cannot
    # race with a send, toggle, or retry that will later persist session state.
    message_lock = _session_message_lock(session_id)
    message_lock.lock.acquire()
    try:
        with session_lifecycle_lock:
            message_lock.retired = True
            if not sessions.delete(session_id):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
            agent_log_store.delete_session(session_id)
            working_memory.delete(session_id)
            pending_memory_repository.delete(session_id)
            pending_memory.pop(session_id, None)
            for key in [key for key in approved_memory_mutations if key[0] == session_id]:
                approved_memory_mutations.pop(key, None)
    finally:
        message_lock.lock.release()
        _release_session_message_lock(message_lock)


@app.get("/sessions/{session_id}/working-memory", response_model=list[WorkingMemoryItem])
async def list_working_memory(session_id: str) -> list[WorkingMemoryItem]:
    await _get_session(session_id)
    try:
        return await run_in_threadpool(working_memory.load, session_id)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail="Working memory is unavailable") from error


@app.patch(
    "/sessions/{session_id}/working-memory/{item_id}", response_model=WorkingMemoryMutationResponse
)
async def update_working_memory(
    session_id: str, item_id: str, request: LongTermMemoryUpdate
) -> WorkingMemoryMutationResponse:
    return await run_in_threadpool(_update_working_memory, session_id, item_id, request)


def _update_working_memory(
    session_id: str, item_id: str, request: LongTermMemoryUpdate
) -> WorkingMemoryMutationResponse:
    with _session_mutation_lock(session_id):
        _get_session_locked(session_id)
        items = working_memory.load(session_id)
        for index, item in enumerate(items):
            if item.id == item_id:
                updated = item.model_copy(
                    update={
                        **request.model_dump(exclude_none=True),
                        "updated_at": datetime.now(UTC),
                    }
                )
                items[index] = updated
                working_memory.save(session_id, items)
                return WorkingMemoryMutationResponse(
                    **updated.model_dump(),
                    memory_events=[
                        MemoryEvent(
                            id=str(uuid.uuid4()), scope="working", action="updated", key=updated.key
                        )
                    ],
                )
        raise HTTPException(status_code=404, detail="Unknown working memory item")


@app.delete(
    "/sessions/{session_id}/working-memory/{item_id}",
    response_model=WorkingMemoryCollectionResponse,
)
async def delete_working_memory(session_id: str, item_id: str) -> WorkingMemoryCollectionResponse:
    return await run_in_threadpool(_delete_working_memory, session_id, item_id)


def _delete_working_memory(session_id: str, item_id: str) -> WorkingMemoryCollectionResponse:
    with _session_mutation_lock(session_id):
        _get_session_locked(session_id)
        items = working_memory.load(session_id)
        deleted = next((item for item in items if item.id == item_id), None)
        retained = [item for item in items if item.id != item_id]
        if deleted is None:
            raise HTTPException(status_code=404, detail="Unknown working memory item")
        working_memory.save(session_id, retained)
        return WorkingMemoryCollectionResponse(
            working_memory=retained,
            memory_events=[
                MemoryEvent(
                    id=str(uuid.uuid4()), scope="working", action="deleted", key=deleted.key
                )
            ],
        )


@app.delete("/sessions/{session_id}/working-memory", response_model=WorkingMemoryCollectionResponse)
async def clear_working_memory(session_id: str) -> WorkingMemoryCollectionResponse:
    return await run_in_threadpool(_clear_working_memory, session_id)


def _clear_working_memory(session_id: str) -> WorkingMemoryCollectionResponse:
    with _session_mutation_lock(session_id):
        _get_session_locked(session_id)
        working_memory.save(session_id, [])
        return WorkingMemoryCollectionResponse(
            memory_events=[MemoryEvent(id=str(uuid.uuid4()), scope="working", action="cleared")]
        )


@app.post(
    "/sessions/{session_id}/working-memory/undo", response_model=WorkingMemoryCollectionResponse
)
async def undo_working_memory(session_id: str) -> WorkingMemoryCollectionResponse:
    return await run_in_threadpool(_undo_working_memory, session_id)


def _undo_working_memory(session_id: str) -> WorkingMemoryCollectionResponse:
    with _session_mutation_lock(session_id):
        _get_session_locked(session_id)
        restored = working_memory.undo_last(session_id)
        if restored is None:
            raise HTTPException(
                status_code=404, detail="No automatic working memory change to undo"
            )
        return WorkingMemoryCollectionResponse(
            working_memory=restored,
            memory_events=[
                MemoryEvent(
                    id=str(uuid.uuid4()),
                    scope="working",
                    action="updated",
                    message="Last automatic change undone",
                )
            ],
        )


@app.get("/sessions/{session_id}/memory/pending", response_model=list[PendingMemorySuggestion])
async def list_pending_memory(session_id: str) -> list[PendingMemorySuggestion]:
    await _get_session(session_id)
    return await run_in_threadpool(pending_memory_repository.load, session_id)


@app.post(
    "/sessions/{session_id}/memory/pending/{candidate_id}/approve",
    response_model=LongTermMemoryMutationResponse,
)
async def approve_memory(session_id: str, candidate_id: str) -> LongTermMemoryMutationResponse:
    return await run_in_threadpool(_approve_memory, session_id, candidate_id)


def _approve_memory(session_id: str, candidate_id: str) -> LongTermMemoryMutationResponse:
    with _session_mutation_lock(session_id):
        session = _get_session_locked(session_id)
        try:
            validate_path_identifier(candidate_id, "candidate ID")
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid candidate ID") from error
        if session.profile_name is None:
            raise HTTPException(
                status_code=409, detail="Long-term memory is unavailable without a profile"
            )
        cached = approved_memory_mutations.get((session_id, candidate_id))
        if cached is not None:
            return cached
        suggestions = pending_memory_repository.load(session_id)
        suggestion = next((item for item in suggestions if item.id == candidate_id), None)
        if suggestion is None or (
            suggestion.candidate.action in {"create", "update"}
            and suggestion.candidate.value is None
        ):
            raise HTTPException(status_code=404, detail="Unknown pending memory suggestion")
        candidate = suggestion.candidate
        if candidate.scope != "long_term" or candidate.action not in {"create", "update", "delete"}:
            raise HTTPException(status_code=409, detail="Invalid long-term memory suggestion")
        existing = profile_memory.load(session.profile_name)
        target = next((item for item in existing if item.id == candidate.target_id), None)
        if candidate.action == "delete":
            if candidate.target_id is None:
                raise HTTPException(status_code=409, detail="Delete suggestions require a target")
            if target is None:
                raise HTTPException(status_code=404, detail="Unknown long-term memory target")
            profile_memory.delete_item(session.profile_name, target.id)
            item = target
            action = "approved"
        elif candidate.action == "update":
            if candidate.target_id is None:
                raise HTTPException(status_code=409, detail="Update suggestions require a target")
            if target is None:
                raise HTTPException(status_code=404, detail="Unknown long-term memory target")
            item = profile_memory.update(
                session.profile_name,
                target.id,
                {
                    "category": candidate.category,
                    "key": candidate.key,
                    "value": candidate.value,
                    "updated_at": datetime.now(UTC),
                },
            )
            action = "approved"
        else:
            if candidate.target_id is not None or any(
                item.key == candidate.key for item in existing
            ):
                raise HTTPException(
                    status_code=409, detail="Create suggestion conflicts with existing memory"
                )
            now = datetime.now(UTC)
            item = LongTermMemoryItem(
                id=str(uuid.uuid4()),
                category=candidate.category,
                key=candidate.key,
                value=candidate.value or "",
                created_at=now,
                updated_at=now,
            )
            profile_memory.create(session.profile_name, item)
            action = "approved"
        remaining = [current for current in suggestions if current.id != candidate_id]
        pending_memory_repository.save(session_id, remaining)
        pending_memory[session_id] = remaining
        result = LongTermMemoryMutationResponse(
            **item.model_dump(),
            memory_events=[
                MemoryEvent(
                    id=str(uuid.uuid4()),
                    scope="long_term",
                    action=action,
                    key=item.key,
                    candidate_id=candidate_id,
                )
            ],
        )
        _cache_approved_memory_mutation((session_id, candidate_id), result)
        return result


@app.post(
    "/sessions/{session_id}/memory/pending/{candidate_id}/reject",
    response_model=WorkingMemoryCollectionResponse,
)
async def reject_memory(session_id: str, candidate_id: str) -> WorkingMemoryCollectionResponse:
    return await run_in_threadpool(_reject_memory, session_id, candidate_id)


def _reject_memory(session_id: str, candidate_id: str) -> WorkingMemoryCollectionResponse:
    with _session_mutation_lock(session_id):
        _get_session_locked(session_id)
        try:
            validate_path_identifier(candidate_id, "candidate ID")
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid candidate ID") from error
        suggestions = pending_memory_repository.load(session_id)
        if not any(item.id == candidate_id for item in suggestions):
            return WorkingMemoryCollectionResponse()
        remaining = [item for item in suggestions if item.id != candidate_id]
        pending_memory_repository.save(session_id, remaining)
        pending_memory[session_id] = remaining
        return WorkingMemoryCollectionResponse(
            memory_events=[
                MemoryEvent(
                    id=str(uuid.uuid4()),
                    scope="long_term",
                    action="rejected",
                    candidate_id=candidate_id,
                )
            ]
        )


@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str) -> None:
    if agents.pop(agent_id, None) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")


def generate_session_title(
    session_id: str,
    agent_log_id: str | None = None,
) -> None:
    """Generate a title without adding title-generation messages to the chat history."""
    session = sessions.load(session_id)
    if session is None or session.title is not None or len(session.messages) < 2:
        return
    source = session.messages[:2]
    title_request = ChatMessage(
        role="user",
        content=(
            "Create a concise Russian title for this chat, between 2 and 6 words. "
            "Describe the topic only.\n\n"
            f"User: {source[0].content}\nAssistant: {source[1].content}"
        ),
    )
    config = LLMConfig(
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
    try:
        if agent_log_id is None:
            response = router.complete([title_request], config)
        else:
            with agent_log_turn(
                session_id,
                agent_log_id,
                provider=config.provider,
                model=config.model,
                operation="title",
            ):
                with agent_log_operation(
                    "title",
                    provider=config.provider,
                    model=config.model,
                ):
                    response = router.complete([title_request], config)
    except ProviderError:
        return
    data = response.structured_data
    title = data.get("title") if isinstance(data, dict) else None
    if not isinstance(title, str):
        return
    normalized = " ".join(title.split())[:80]
    if not normalized:
        return
    with session_lifecycle_lock:
        latest = sessions.load(session_id)
        if latest is None or latest.title is not None:
            return
        latest.title = normalized
        latest.updated_at = datetime.now(UTC)
        sessions.save(latest)


def _save_agent_state(session: ChatSession, agent: Agent) -> None:
    # Serialize the complete save with DELETE so a completed request cannot
    # recreate any part of a deleted session.
    with session_lifecycle_lock:
        if sessions.load(session.id) is None:
            return
        session.messages = agent.history
        session.context = agent.context
        session.updated_at = datetime.now(UTC)
        sessions.save(session)
        if session.config.context_management.strategy == ContextStrategyName.STICKY_FACTS:
            sessions.save_facts(session.id, agent.facts)
        working_memory.save_preserving_undo(session.id, agent.working_memory)
        pending_memory_repository.save(session.id, agent.pending_memory)


def _finish_agent_log(
    agent_log_id: str,
    *,
    provider: ProviderName | None = None,
    model: str | None = None,
    usage: dict[str, int] | None = None,
    status: str,
    error: str | None = None,
) -> None:
    agent_log_store.finish_turn(
        agent_log_id,
        provider=provider,
        model=model,
        usage=usage,
        status=status,
        error=error,
    )


def _ask_agent(
    session_id: str,
    agent: Agent,
    content: str,
    agent_log_id: str | None = None,
    session_lock_held: bool = False,
) -> LLMResponse:
    message_lock = None if session_lock_held else _session_message_lock(session_id)
    if message_lock is not None:
        message_lock.lock.acquire()
    try:
        with session_lifecycle_lock:
            if sessions.load(session_id) is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
        if agent_log_id is None:
            return agent.ask(content)
        with agent_log_turn(
            session_id,
            agent_log_id,
            provider=agent.config.provider,
            model=agent.config.model,
        ):
            return agent.ask(content, agent_log_id=agent_log_id)
    finally:
        if message_lock is not None:
            message_lock.lock.release()
            _release_session_message_lock(message_lock)


def _retry_agent(
    session_id: str,
    agent: Agent,
    agent_log_id: str | None = None,
    session_lock_held: bool = False,
) -> LLMResponse:
    message_lock = None if session_lock_held else _session_message_lock(session_id)
    if message_lock is not None:
        message_lock.lock.acquire()
    try:
        with session_lifecycle_lock:
            if sessions.load(session_id) is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
        if agent_log_id is None:
            return agent.retry_summarization()
        with agent_log_turn(
            session_id,
            agent_log_id,
            provider=agent.config.provider,
            model=agent.config.model,
            operation="retry",
        ):
            return agent.retry_summarization(agent_log_id=agent_log_id)
    finally:
        if message_lock is not None:
            message_lock.lock.release()
            _release_session_message_lock(message_lock)


def _long_term_memory_for_session(
    session: ChatSession, facts: dict[str, str]
) -> list[LongTermMemoryItem]:
    if session.profile_name is None or not session.long_term_memory_enabled:
        return []
    items = profile_memory.load(session.profile_name)
    if session.config.context_management.strategy == ContextStrategyName.STICKY_FACTS:
        return [item for item in items if item.key not in facts]
    return items


def run() -> None:
    import uvicorn

    uvicorn.run("copia.api.service:app", host="127.0.0.1", port=8000, reload=False)
