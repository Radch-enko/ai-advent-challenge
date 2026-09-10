from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderName(str, Enum):
    OPENAI = "openai"
    GIGACHAT = "gigachat"


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_output_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    top_k: int | None = Field(default=None, gt=0)


class StructuredOutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    json_schema: dict[str, Any] = Field(alias="schema", serialization_alias="schema")
    strict: bool = True


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    model: str = Field(min_length=1)
    system_prompt: str | None = None
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    structured_output: StructuredOutputConfig | None = None
    provider_options: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(LLMConfig):
    name: str = Field(min_length=1)
    description: str | None = None
    avatar_path: str | None = None


class CompletionConfig(LLMConfig):
    """Configuration for a direct, stateless LLM request."""


class ProviderModel(BaseModel):
    id: str
    context_window: int | None = None


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str
    usage: dict[str, int] | None = None
    context_window: int | None = Field(default=None, gt=0)


class ProviderTrace(BaseModel):
    status_code: int
    request_body: dict[str, Any]
    response_body: dict[str, Any]


class LLMResponse(BaseModel):
    content: str
    provider: ProviderName
    model: str
    usage: dict[str, int] | None = None
    context_window: int | None = Field(default=None, gt=0)
    structured_data: dict[str, Any] | list[Any] | None = None
    trace: ProviderTrace | None = None


class ProviderCapabilities(BaseModel):
    provider: ProviderName
    supported_parameters: list[str]
    supports_structured_output: bool
