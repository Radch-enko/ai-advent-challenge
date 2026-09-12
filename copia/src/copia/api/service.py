from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator

from ..data.providers.llm import ProviderError
from ..data.profiles_repository import ProfilesRepository
from ..data.sessions_repository import SessionsRepository
from ..domain.models.agent import Agent, AgentFactory, SummarizationFailed, SummarizationRetryRequired
from ..domain.models.config import AgentConfig, ChatMessage, CompletionConfig, GenerationConfig, LLMConfig, LLMResponse, ProviderCapabilities, ProviderModel, ProviderName, StructuredOutputConfig
from ..domain.models.session import ChatSession, ChatSessionSummary, SummarizationEvent
from ..domain.services.router import LLMRouter

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
profiles_path = Path(os.getenv("COPIA_PROFILES_PATH", PROJECT_ROOT / "profiles.json"))
router = LLMRouter()
factory = AgentFactory(router, ProfilesRepository(profiles_path))
agents: dict[str, Agent] = {}
sessions = SessionsRepository(Path(os.getenv("COPIA_SESSIONS_PATH", "~/.copia/sessions")))

app = FastAPI(title="Copia API", version="0.1.0")


def provider_error_detail(error: ProviderError) -> dict[str, object]:
    return {
        "message": str(error),
        "provider_trace": {
            "status_code": error.status_code,
            "request_body": error.request_body,
            "response_body": error.response_body,
        },
    }


class CreateAgentRequest(BaseModel):
    profile_name: str | None = None
    config: AgentConfig | None = None

    @model_validator(mode="after")
    def require_one_source(self) -> "CreateAgentRequest":
        if (self.profile_name is None) == (self.config is None):
            raise ValueError("Provide exactly one of profile_name or config")
        return self


class CreateAgentResponse(BaseModel):
    agent_id: str
    config: AgentConfig


class MessageRequest(BaseModel):
    content: str = Field(min_length=1)
    config: AgentConfig | None = None


class ContextManagementUpdate(BaseModel):
    enabled: bool


class MessageResponse(BaseModel):
    response: LLMResponse
    summarization_events: list[SummarizationEvent] = Field(default_factory=list)


class CompletionRequest(BaseModel):
    config: CompletionConfig
    messages: list[ChatMessage] = Field(min_length=1)


class CreateSessionRequest(BaseModel):
    profile_name: str | None = None
    config: AgentConfig | None = None

    @model_validator(mode="after")
    def require_one_source(self) -> "CreateSessionRequest":
        if (self.profile_name is None) == (self.config is None):
            raise ValueError("Provide exactly one of profile_name or config")
        return self


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/profiles")
def profiles() -> dict[str, AgentConfig]:
    return factory.profiles()


@app.get("/providers/{provider_name}/capabilities")
def capabilities(provider_name: ProviderName) -> ProviderCapabilities:
    try:
        return router.capabilities(provider_name)
    except ProviderError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.get("/providers/{provider_name}/models", response_model=list[ProviderModel])
async def models(provider_name: ProviderName) -> list[ProviderModel]:
    try:
        return await run_in_threadpool(router.models, provider_name)
    except ProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=provider_error_detail(error)) from error


@app.post("/completions", response_model=MessageResponse)
async def completion(request: CompletionRequest) -> MessageResponse:
    messages = list(request.messages)
    if request.config.system_prompt:
        messages.insert(0, ChatMessage(role="system", content=request.config.system_prompt))
    try:
        response = await run_in_threadpool(router.complete, messages, request.config)
    except ProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=provider_error_detail(error)) from error
    return MessageResponse(response=response)


@app.post("/agents", response_model=CreateAgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(request: CreateAgentRequest) -> CreateAgentResponse:
    try:
        agent = (
            factory.create_from_profile(request.profile_name)
            if request.profile_name is not None
            else factory.create(request.config)  # type: ignore[arg-type]
        )
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    agent_id = str(uuid.uuid4())
    agents[agent_id] = agent
    return CreateAgentResponse(agent_id=agent_id, config=agent.config)


@app.post("/agents/{agent_id}/messages", response_model=MessageResponse)
async def send_message(agent_id: str, request: MessageRequest) -> MessageResponse:
    agent = agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
    try:
        response = await run_in_threadpool(agent.ask, request.content)
    except ProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=provider_error_detail(error)) from error
    return MessageResponse(response=response)


@app.get("/sessions", response_model=list[ChatSessionSummary])
def list_sessions() -> list[ChatSessionSummary]:
    return sessions.list()


@app.post("/sessions", response_model=ChatSession, status_code=status.HTTP_201_CREATED)
def create_session(request: CreateSessionRequest) -> ChatSession:
    try:
        config = (
            factory.profiles()[request.profile_name]
            if request.profile_name is not None
            else request.config
        )
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown profile: {request.profile_name}") from error
    assert config is not None
    now = datetime.now(UTC)
    session = ChatSession(
        id=str(uuid.uuid4()),
        config=config,
        profile_name=request.profile_name,
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)
    return session


@app.get("/sessions/{session_id}", response_model=ChatSession)
def get_session(session_id: str) -> ChatSession:
    session = sessions.load(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
    return session


@app.patch("/sessions/{session_id}/context-management", response_model=ChatSession)
def update_session_context_management(session_id: str, request: ContextManagementUpdate) -> ChatSession:
    session = get_session(session_id)
    session.config.context_management.enabled = request.enabled
    session.updated_at = datetime.now(UTC)
    sessions.save(session)
    return session


@app.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def send_session_message(session_id: str, request: MessageRequest, background_tasks: BackgroundTasks) -> MessageResponse:
    session = get_session(session_id)
    if request.config is not None and session.profile_name is None:
        session.config = request.config
    agent = Agent(config=session.config, router=router, history=session.messages, context=session.context)
    try:
        response = await run_in_threadpool(agent.ask, request.content)
    except SummarizationFailed as error:
        _save_agent_state(session, agent)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": str(error),
                "code": "summarization_failed",
                "summarization_event": error.event.model_dump(mode="json"),
            },
        ) from error
    except SummarizationRetryRequired as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ProviderError as error:
        _save_agent_state(session, agent)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=provider_error_detail(error)) from error

    _save_agent_state(session, agent)
    if session.title is None:
        background_tasks.add_task(generate_session_title, session.id)
    return MessageResponse(response=response, summarization_events=agent.operation_events)


@app.post("/sessions/{session_id}/summarization/retry", response_model=MessageResponse)
async def retry_session_summarization(session_id: str) -> MessageResponse:
    session = get_session(session_id)
    agent = Agent(config=session.config, router=router, history=session.messages, context=session.context)
    try:
        response = await run_in_threadpool(agent.retry_summarization)
    except SummarizationFailed as error:
        _save_agent_state(session, agent)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": str(error),
                "code": "summarization_failed",
                "summarization_event": error.event.model_dump(mode="json"),
            },
        ) from error
    except SummarizationRetryRequired as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ProviderError as error:
        _save_agent_state(session, agent)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=provider_error_detail(error)) from error

    _save_agent_state(session, agent)
    return MessageResponse(response=response, summarization_events=agent.operation_events)


@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str) -> None:
    if not sessions.delete(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")


@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str) -> None:
    if agents.pop(agent_id, None) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")


def generate_session_title(session_id: str) -> None:
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
    latest = sessions.load(session_id)
    if latest is None or latest.title is not None:
        return
    latest.title = normalized
    latest.updated_at = datetime.now(UTC)
    sessions.save(latest)


def _save_agent_state(session: ChatSession, agent: Agent) -> None:
    session.messages = agent.history
    session.context = agent.context
    session.updated_at = datetime.now(UTC)
    sessions.save(session)


def run() -> None:
    import uvicorn

    uvicorn.run("copia.api.service:app", host="127.0.0.1", port=8000, reload=False)
