import json
import logging
import math
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from code_assistance.config import AppConfig, api_key_from_environment
from code_assistance.errors import ConfigurationError, ProviderError
from code_assistance.http_retry import RETRYABLE_HTTP_STATUSES, RetryPolicy, call_with_retry
from code_assistance.models import ToolDefinition

LOGGER = logging.getLogger(__name__)
RequestResult = TypeVar("RequestResult")
_SECRET_VALUE = re.compile(
    r"(?i)\b(api[_ -]?key|authorization|token|secret)\b(\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"
)
_URL_CREDENTIALS = re.compile(r"(?i)(https?://)[^/@\s]+@")
_URL_QUERY = re.compile(r"(https?://[^\s?#]+)\?[^\s#]+")


class _IncompleteStructuredResponseError(ProviderError):
    """A streamed response ended before OpenAI emitted its completion event."""


def _connection_failure_details(error: Exception) -> str | None:
    if not isinstance(error, APIConnectionError):
        return None

    request = error.request
    request_path = getattr(request.url, "path", "unknown")
    request_description = f"request={request.method} {request_path}"
    causes: list[str] = []
    current = error.__cause__ or error.__context__
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(causes) < 8:
        seen.add(id(current))
        cause = f"{type(current).__module__}.{type(current).__name__}"
        message = str(current).strip()
        if message:
            message = _URL_CREDENTIALS.sub(r"\1<redacted>@", message)
            message = _URL_QUERY.sub(r"\1?<redacted>", message)
            message = _SECRET_VALUE.sub(r"\1\2<redacted>", message)
            cause += f": {message[:300]}"
        causes.append(cause)
        current = current.__cause__ or current.__context__

    cause_chain = " <- ".join(causes) if causes else "unavailable"
    return f"{request_description} cause_chain={cause_chain}"


class OpenAIProvider:
    def __init__(
        self, config: AppConfig, env_file: Path | None = None, *, max_retries: int = 0
    ) -> None:
        self.config = config
        self.env_file = env_file
        self.max_retries = max_retries
        self._client: OpenAI | None = None

    def _request(self, operation: str, request: Callable[[], RequestResult]) -> RequestResult:
        policy = RetryPolicy(max_attempts=self.max_retries + 1)
        return call_with_retry(
            request,
            operation=f"OpenAI {operation}",
            is_retryable=self._is_retryable,
            policy=policy,
            logger=LOGGER,
            retry_after=self._retry_after,
            failure_details=_connection_failure_details,
        )

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        if isinstance(error, _IncompleteStructuredResponseError):
            return True
        if isinstance(error, (APIConnectionError, APITimeoutError, RateLimitError)):
            return True
        return isinstance(error, APIStatusError) and error.status_code in RETRYABLE_HTTP_STATUSES

    @staticmethod
    def _retry_after(error: Exception) -> float | None:
        if not isinstance(error, APIStatusError):
            return None
        value = error.response.headers.get("retry-after")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=api_key_from_environment(self.env_file),
                base_url=self.config.base_url,
                timeout=self.config.request_timeout_seconds,
                max_retries=0,
            )
        return self._client

    def check_connection(self) -> None:
        """Verify API-key access and connectivity with GET /models."""
        try:
            self._request("connection check", lambda: self._get_client().models.list())
        except ConfigurationError:
            raise
        except AuthenticationError as exc:
            raise ProviderError(
                "OpenAI rejected the API key during the connection check. "
                "Check OPENAI_API_KEY and its access."
            ) from exc
        except RateLimitError as exc:
            raise ProviderError(
                "OpenAI rate limit reached during the connection check. "
                "Wait briefly or check the account's usage limits."
            ) from exc
        except APITimeoutError as exc:
            raise ProviderError(
                "The OpenAI connection check timed out. Check the endpoint or timeout_seconds."
            ) from exc
        except APIConnectionError as exc:
            raise ProviderError(
                "Could not connect to the configured OpenAI endpoint. "
                "Check the network and endpoint."
            ) from exc
        except APIStatusError as exc:
            raise ProviderError(
                f"OpenAI returned HTTP {exc.status_code} during the connection check."
            ) from exc
        except OpenAIError as exc:
            raise ProviderError("The OpenAI connection check failed.") from exc

    def generate(
        self,
        instructions: str,
        prompt: str,
        *,
        text_format: Mapping[str, object] | None = None,
    ) -> str:
        try:
            if text_format is None:
                response = self._request(
                    "response",
                    lambda: self._get_client().responses.create(
                        model=self.config.chat_model,
                        instructions=instructions,
                        input=prompt,
                    ),
                )
            else:
                response = self._request(
                    "structured response",
                    lambda: self._consume_structured_response_stream(
                        instructions,
                        prompt,
                        text_format,
                    ),
                )
        except ConfigurationError:
            raise
        except AuthenticationError as exc:
            raise ProviderError(
                "OpenAI rejected the API key. Check OPENAI_API_KEY and try again."
            ) from exc
        except RateLimitError as exc:
            raise ProviderError(
                "OpenAI rate limit reached. Wait briefly or check the account's usage limits."
            ) from exc
        except APITimeoutError as exc:
            raise ProviderError(
                "The OpenAI request timed out. Check the endpoint or increase timeout_seconds."
            ) from exc
        except APIConnectionError as exc:
            raise ProviderError(
                "Could not connect to the configured OpenAI endpoint. "
                "Check the network and endpoint."
            ) from exc
        except BadRequestError as exc:
            raise ProviderError(
                "OpenAI rejected the chat request. Check the configured chat model."
            ) from exc
        except APIStatusError as exc:
            raise ProviderError(
                f"OpenAI returned HTTP {exc.status_code}. Try again later."
            ) from exc
        except OpenAIError as exc:
            raise ProviderError(
                "The OpenAI chat request failed. Check the model and endpoint."
            ) from exc

        answer = response.output_text.strip()
        if not answer:
            status = getattr(response, "status", None)
            incomplete_details = getattr(response, "incomplete_details", None)
            reason = getattr(incomplete_details, "reason", None)
            if status == "incomplete" and reason == "max_output_tokens":
                raise ProviderError(
                    "OpenAI stopped generation at a token limit before returning visible text. "
                    "Check the selected model's output and context limits."
                )
            if status == "incomplete" and reason == "content_filter":
                raise ProviderError(
                    "OpenAI did not return chat text because the response was blocked by its "
                    "content filter."
                )

            safe_statuses = {"completed", "incomplete", "failed", "cancelled"}
            safe_reasons = {"max_output_tokens", "content_filter"}
            response_details = []
            if status in safe_statuses:
                response_details.append(f"status: {status}")
            if reason in safe_reasons:
                response_details.append(f"reason: {reason}")
            details = f" ({', '.join(response_details)})" if response_details else ""
            raise ProviderError(
                "OpenAI returned no readable chat text"
                f"{details}. Check that the configured chat model and endpoint support "
                "the Responses API."
            )
        return answer

    def _consume_structured_response_stream(
        self,
        instructions: str,
        prompt: str,
        text_format: Mapping[str, object],
    ) -> Any:
        """Consume a complete SSE response inside the retry boundary."""
        stream = self._get_client().responses.create(
            model=self.config.chat_model,
            instructions=instructions,
            input=prompt,
            text={"format": cast(Any, text_format)},
            stream=True,
        )
        completed_response: Any | None = None
        event_count = 0
        with stream as events:
            for event in events:
                event_count += 1
                event_type = getattr(event, "type", None)
                if event_count == 1:
                    LOGGER.info("OpenAI structured response SSE first_event=%s", event_type)
                if event_type == "response.completed":
                    completed_response = getattr(event, "response", None)
                elif event_type in {"response.failed", "response.incomplete", "error"}:
                    raise ProviderError("OpenAI did not complete the streamed structured response.")

        if completed_response is None:
            raise _IncompleteStructuredResponseError(
                "OpenAI ended the streamed structured response without a completion event."
            )
        LOGGER.info("OpenAI structured response SSE completed events=%d", event_count)
        return completed_response

    def generate_with_tools(
        self,
        instructions: str,
        prompt: str,
        tools: Sequence[ToolDefinition],
        call_tool: Callable[[str, dict[str, object]], str],
    ) -> str:
        if not tools:
            return self.generate(instructions, prompt)
        definitions: list[dict[str, object]] = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": False,
            }
            for tool in tools
        ]
        input_items: list[Any] = [{"role": "user", "content": prompt}]
        call_count = 0
        for _ in range(5):
            try:
                response = self._request(
                    "tool response",
                    lambda: self._get_client().responses.create(
                        model=self.config.chat_model,
                        instructions=instructions,
                        input=cast(Any, input_items),
                        tools=cast(Any, definitions),
                        tool_choice="auto",
                    ),
                )
            except ConfigurationError:
                raise
            except AuthenticationError as exc:
                raise ProviderError("OpenAI rejected the API key. Check OPENAI_API_KEY.") from exc
            except RateLimitError as exc:
                raise ProviderError("OpenAI rate limit reached. Wait and retry.") from exc
            except APITimeoutError as exc:
                raise ProviderError("The OpenAI request timed out.") from exc
            except APIConnectionError as exc:
                raise ProviderError("Could not connect to the configured OpenAI endpoint.") from exc
            except BadRequestError as exc:
                raise ProviderError(
                    "OpenAI rejected the tool request. Check the chat model and tool schema."
                ) from exc
            except APIStatusError as exc:
                raise ProviderError(
                    f"OpenAI returned HTTP {exc.status_code} during the tool request."
                ) from exc
            except OpenAIError as exc:
                raise ProviderError("The OpenAI tool request failed.") from exc

            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                answer = response.output_text.strip()
                if not answer:
                    raise ProviderError("OpenAI returned no readable chat text.")
                return answer
            input_items.extend(response.output)
            for item in calls:
                call_count += 1
                if call_count > 8:
                    raise ProviderError("OpenAI requested too many tool calls.")
                try:
                    arguments = json.loads(item.arguments)
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ProviderError("OpenAI returned invalid tool arguments.") from exc
                if not isinstance(arguments, dict) or any(
                    not isinstance(key, str) for key in arguments
                ):
                    raise ProviderError("OpenAI returned invalid tool arguments.")
                result = call_tool(item.name, arguments)
                input_items.append(
                    {"type": "function_call_output", "call_id": item.call_id, "output": result}
                )
        raise ProviderError("OpenAI did not finish after the allowed tool rounds.")

    def embed(
        self,
        texts: Sequence[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        try:
            embeddings = self._get_client().embeddings
            if dimensions is None:
                response = self._request(
                    "embeddings",
                    lambda: embeddings.create(
                        model=self.config.embedding_model,
                        input=list(texts),
                    ),
                )
            else:
                response = self._request(
                    "embeddings",
                    lambda: embeddings.create(
                        model=self.config.embedding_model,
                        input=list(texts),
                        dimensions=dimensions,
                    ),
                )
        except ConfigurationError:
            raise
        except AuthenticationError as exc:
            raise ProviderError(
                "OpenAI rejected the API key. Check OPENAI_API_KEY and try again."
            ) from exc
        except RateLimitError as exc:
            raise ProviderError(
                "OpenAI rate limit reached while creating embeddings. Wait and retry."
            ) from exc
        except APITimeoutError as exc:
            raise ProviderError(
                "The OpenAI embedding request timed out. "
                "Check the endpoint or increase timeout_seconds."
            ) from exc
        except APIConnectionError as exc:
            raise ProviderError(
                "Could not connect to the configured OpenAI endpoint while creating embeddings."
            ) from exc
        except BadRequestError as exc:
            raise ProviderError(
                "OpenAI rejected the embedding request. Check the embedding model and dimensions."
            ) from exc
        except APIStatusError as exc:
            raise ProviderError(
                f"OpenAI returned HTTP {exc.status_code} while creating embeddings."
            ) from exc
        except OpenAIError as exc:
            raise ProviderError(
                "The OpenAI embedding request failed. Check the model and endpoint."
            ) from exc

        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [[float(value) for value in item.embedding] for item in ordered]
        if len(vectors) != len(texts):
            raise ProviderError("OpenAI returned an unexpected number of embeddings.")
        if not vectors or not vectors[0]:
            raise ProviderError("OpenAI returned an empty embedding.")
        dimension = len(vectors[0])
        if any(len(vector) != dimension for vector in vectors):
            raise ProviderError("OpenAI returned embeddings with inconsistent dimensions.")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise ProviderError("OpenAI returned an invalid embedding value.")
        return vectors


class OpenAIStructuredGenerator:
    """Use strict JSON Schema for one chat boundary without changing CLI responses."""

    def __init__(self, provider: OpenAIProvider, name: str, schema: Mapping[str, object]) -> None:
        self.provider = provider
        self.name = name
        self.schema = schema

    def generate(self, instructions: str, prompt: str) -> str:
        return self.provider.generate(
            instructions,
            prompt,
            text_format={
                "type": "json_schema",
                "name": self.name,
                "strict": True,
                "schema": self.schema,
            },
        )
