import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

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
from code_assistance.models import ToolDefinition


class OpenAIProvider:
    def __init__(self, config: AppConfig, env_file: Path | None = None) -> None:
        self.config = config
        self.env_file = env_file
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=api_key_from_environment(self.env_file),
                base_url=self.config.base_url,
                timeout=self.config.request_timeout_seconds,
                max_retries=0,
            )
        return self._client

    def generate(self, instructions: str, prompt: str) -> str:
        try:
            response = self._get_client().responses.create(
                model=self.config.chat_model,
                instructions=instructions,
                input=prompt,
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
                response = self._get_client().responses.create(
                    model=self.config.chat_model,
                    instructions=instructions,
                    input=cast(Any, input_items),
                    tools=cast(Any, definitions),
                    tool_choice="auto",
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
                response = embeddings.create(
                    model=self.config.embedding_model,
                    input=list(texts),
                )
            else:
                response = embeddings.create(
                    model=self.config.embedding_model,
                    input=list(texts),
                    dimensions=dimensions,
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
