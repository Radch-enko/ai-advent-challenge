from __future__ import annotations

import argparse
import os
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

DEFAULT_API_URL = "http://127.0.0.1:8000"
HTTP_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_ERROR_MESSAGE_LENGTH = 1000


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    occurred_at: datetime
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    amount_rub: Decimal = Field(gt=0)
    merchant: str | None = None
    payment_method: str | None = None
    note: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value

    @field_validator("amount_rub")
    @classmethod
    def require_kopeck_precision(cls, value: Decimal) -> Decimal:
        if value.as_tuple().exponent < -2:
            raise ValueError("amount_rub must have at most two decimal places")
        return value

    @field_validator("merchant", "payment_method", "note")
    @classmethod
    def reject_empty_optional_strings(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("value must not be empty")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = [tag.strip() for tag in value]
        if any(not tag for tag in normalized):
            raise ValueError("tags must not contain empty values")
        return normalized


class Expense(ExpenseCreate):
    id: UUID
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_created_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone offset")
        return value


class ExpensePage(BaseModel):
    items: list[Expense]
    next_cursor: str | None = None


class ExpenseSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    category: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    merchant: str | None = Field(default=None, min_length=1)
    payment_method: str | None = Field(default=None, min_length=1)
    tags: list[str] = Field(default_factory=list)
    min_amount_rub: Decimal | None = Field(default=None, ge=0)
    max_amount_rub: Decimal | None = Field(default=None, ge=0)
    text: str | None = Field(default=None, min_length=1)
    page_size: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None

    @field_validator("occurred_from", "occurred_to")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("date filters must include a timezone offset")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = [tag.strip() for tag in value]
        if any(not tag for tag in normalized):
            raise ValueError("tags must not contain empty values")
        return normalized

    @model_validator(mode="after")
    def validate_ranges(self) -> ExpenseSearchRequest:
        if (
            self.occurred_from is not None
            and self.occurred_to is not None
            and self.occurred_from > self.occurred_to
        ):
            raise ValueError("occurred_from must not be later than occurred_to")
        if (
            self.min_amount_rub is not None
            and self.max_amount_rub is not None
            and self.min_amount_rub > self.max_amount_rub
        ):
            raise ValueError("min_amount_rub must not exceed max_amount_rub")
        return self


class CopiaApiClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def search_expenses(self, request: ExpenseSearchRequest) -> ExpensePage:
        payload = await self._request(
            "GET",
            "/expenses",
            params=request.model_dump(mode="json", exclude_none=True),
        )
        return self._validate_response(ExpensePage, payload)

    async def add_expense(self, request: ExpenseCreate) -> Expense:
        payload = await self._request(
            "POST",
            "/expenses",
            json=request.model_dump(mode="json"),
        )
        return self._validate_response(Expense, payload)

    async def _request(self, method: str, path: str, **kwargs: Any) -> object:
        base_url = self._base_url()
        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                timeout=HTTP_TIMEOUT_SECONDS,
                follow_redirects=False,
                transport=self._transport,
                trust_env=False,
            ) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.TimeoutException as error:
            raise ToolError("Copia API request timed out") from error
        except httpx.RequestError as error:
            raise ToolError("Copia API is unavailable") from error

        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ToolError("Copia API response is too large")
        if response.is_error or response.is_redirect:
            raise ToolError(self._error_message(response))
        try:
            return response.json()
        except ValueError as error:
            raise ToolError("Copia API returned an invalid response") from error

    @staticmethod
    def _base_url() -> str:
        raw_url = os.getenv("COPIA_API_URL", DEFAULT_API_URL).strip().rstrip("/")
        parsed = urlsplit(raw_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ToolError("COPIA_API_URL is invalid")
        return raw_url

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, dict) and isinstance(detail.get("message"), str):
                return detail["message"][:MAX_ERROR_MESSAGE_LENGTH]
        return f"Copia API request failed with status {response.status_code}"

    @staticmethod
    def _validate_response(model_type, payload: object):
        try:
            return model_type.model_validate(payload)
        except ValidationError as error:
            raise ToolError("Copia API returned an invalid response") from error


api_client = CopiaApiClient()
server = MCPServer(
    "Copia Finances",
    description="Search and add expenses through the Copia API",
    version="0.1.0",
)


def _validation_error(error: ValidationError) -> ToolError:
    message = error.errors(include_url=False)[0]["msg"]
    return ToolError(str(message)[:MAX_ERROR_MESSAGE_LENGTH])


@server.tool(
    name="search_expenses",
    description="Search expenses using optional filters and cursor pagination.",
    structured_output=True,
)
async def search_expenses(
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    category: str | None = None,
    name: str | None = None,
    merchant: str | None = None,
    payment_method: str | None = None,
    tags: list[str] | None = None,
    min_amount_rub: Decimal | None = None,
    max_amount_rub: Decimal | None = None,
    text: str | None = None,
    page_size: Annotated[int, Field(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> ExpensePage:
    try:
        request = ExpenseSearchRequest(
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            category=category,
            name=name,
            merchant=merchant,
            payment_method=payment_method,
            tags=tags or [],
            min_amount_rub=min_amount_rub,
            max_amount_rub=max_amount_rub,
            text=text,
            page_size=page_size,
            cursor=cursor,
        )
    except ValidationError as error:
        raise _validation_error(error) from error
    return await api_client.search_expenses(request)


@server.tool(
    name="add_expense",
    description="Add one expense to the Copia finances workbook.",
    structured_output=True,
)
async def add_expense(
    occurred_at: datetime,
    name: Annotated[str, Field(min_length=1)],
    category: Annotated[str, Field(min_length=1)],
    amount_rub: Annotated[Decimal, Field(gt=0)],
    merchant: str | None = None,
    payment_method: str | None = None,
    note: str | None = None,
    tags: list[str] | None = None,
) -> Expense:
    try:
        request = ExpenseCreate(
            occurred_at=occurred_at,
            name=name,
            category=category,
            amount_rub=amount_rub,
            merchant=merchant,
            payment_method=payment_method,
            note=note,
            tags=tags or [],
        )
    except ValidationError as error:
        raise _validation_error(error) from error
    return await api_client.add_expense(request)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Copia finances MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.transport == "stdio":
            server.run("stdio")
            return
        server.run(
            "streamable-http",
            host="127.0.0.1",
            port=8001,
            streamable_http_path="/mcp",
        )
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
