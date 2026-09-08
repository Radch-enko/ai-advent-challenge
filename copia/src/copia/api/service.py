from __future__ import annotations

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator

from ..data.providers.llm import ProviderError
from ..data.profiles_repository import ProfilesRepository
from ..domain.models.agent import Agent, AgentFactory
from ..domain.models.config import AgentConfig, ChatMessage, CompletionConfig, LLMResponse, ProviderCapabilities, ProviderModel, ProviderName
from ..domain.services.router import LLMRouter

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
profiles_path = Path(os.getenv("COPIA_PROFILES_PATH", PROJECT_ROOT / "profiles.json"))
router = LLMRouter()
factory = AgentFactory(router, ProfilesRepository(profiles_path))
agents: dict[str, Agent] = {}

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


class MessageResponse(BaseModel):
    response: LLMResponse


class CompletionRequest(BaseModel):
    config: CompletionConfig
    messages: list[ChatMessage] = Field(min_length=1)


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


@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str) -> None:
    if agents.pop(agent_id, None) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")


def run() -> None:
    import uvicorn

    uvicorn.run("copia.api.service:app", host="127.0.0.1", port=8000, reload=False)
