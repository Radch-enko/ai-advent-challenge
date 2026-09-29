from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

os.environ.setdefault("MPLBACKEND", "Agg")

import httpx
from matplotlib import pyplot as plt
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.types import Image
from mcp_types import CallToolResult, TextContent
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


class ExpenseComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_expenses: list[Expense] = Field(default_factory=list)
    previous_expenses: list[Expense] = Field(default_factory=list)
    current_label: str = Field(default="Current period", min_length=1)
    previous_label: str = Field(default="Previous period", min_length=1)


class ExpenseCategoryComparison(BaseModel):
    category: str
    current_total_rub: Decimal
    previous_total_rub: Decimal
    difference_rub: Decimal


class ExpenseChartPoint(BaseModel):
    label: str
    current_total_rub: Decimal
    previous_total_rub: Decimal


class ExpenseComparison(BaseModel):
    current_label: str
    previous_label: str
    current_total_rub: Decimal
    previous_total_rub: Decimal
    difference_rub: Decimal
    percentage_change: Decimal | None
    current_count: int
    previous_count: int
    categories: list[ExpenseCategoryComparison]
    chart_data: list[ExpenseChartPoint]


def _total(expenses: list[Expense]) -> Decimal:
    return sum((expense.amount_rub for expense in expenses), Decimal("0"))


def _category_totals(expenses: list[Expense]) -> dict[str, Decimal]:
    totals: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for expense in expenses:
        totals[expense.category] += expense.amount_rub
    return dict(totals)


def _percentage_change(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == 0:
        return None
    return (current - previous) / previous * Decimal("100")


def compare_expense_periods(request: ExpenseComparisonRequest) -> ExpenseComparison:
    current_total = _total(request.current_expenses)
    previous_total = _total(request.previous_expenses)
    current_categories = _category_totals(request.current_expenses)
    previous_categories = _category_totals(request.previous_expenses)
    categories = [
        ExpenseCategoryComparison(
            category=category,
            current_total_rub=current_categories.get(category, Decimal("0")),
            previous_total_rub=previous_categories.get(category, Decimal("0")),
            difference_rub=current_categories.get(category, Decimal("0"))
            - previous_categories.get(category, Decimal("0")),
        )
        for category in sorted(current_categories.keys() | previous_categories.keys())
    ]
    chart_data = [
        ExpenseChartPoint(
            label=item.category,
            current_total_rub=item.current_total_rub,
            previous_total_rub=item.previous_total_rub,
        )
        for item in categories
    ]
    return ExpenseComparison(
        current_label=request.current_label,
        previous_label=request.previous_label,
        current_total_rub=current_total,
        previous_total_rub=previous_total,
        difference_rub=current_total - previous_total,
        percentage_change=_percentage_change(current_total, previous_total),
        current_count=len(request.current_expenses),
        previous_count=len(request.previous_expenses),
        categories=categories,
        chart_data=chart_data,
    )


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
    description=(
        "Search expenses using filters and cursor pagination. For weekly comparisons, use "
        "separate timezone-aware occurred_from/occurred_to bounds for each calendar week in "
        "the current local timezone. Bounds are inclusive. Set page_size to 100 and follow "
        "cursor until next_cursor is null; do not infer missing expenses."
    ),
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
    name="compare_expense_periods",
    description=(
        "Compare two complete expense lists using deterministic totals and category analysis. "
        "Pass current_expenses and previous_expenses as arrays of complete Expense objects "
        "returned by search_expenses; do not group them by date or summarize them manually. "
        "Set labels to the exact periods. Pass this tool's complete result as the comparison "
        "argument to save_expense_chart."
    ),
    structured_output=True,
)
async def compare_expense_periods_tool(
    current_expenses: list[Expense],
    previous_expenses: list[Expense],
    current_label: str = "Current period",
    previous_label: str = "Previous period",
) -> ExpenseComparison:
    return compare_expense_periods(
        ExpenseComparisonRequest(
            current_expenses=current_expenses,
            previous_expenses=previous_expenses,
            current_label=current_label,
            previous_label=previous_label,
        )
    )


@server.tool(
    name="save_expense_chart",
    description=(
        "Render an expense period comparison as a PNG chart. Pass the complete "
        "ExpenseComparison result from compare_expense_periods as the comparison argument; "
        "do not construct or recalculate the comparison yourself. After the tool returns, "
        "include the exact artifact URL from its result once in your final answer using "
        "Markdown image syntax: ![Expense comparison](URL). Never use the filename as the URL."
    ),
)
async def save_expense_chart(comparison: ExpenseComparison) -> CallToolResult:
    figure, axis = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    labels = [point.label for point in comparison.chart_data]
    previous = [float(point.previous_total_rub) for point in comparison.chart_data]
    current = [float(point.current_total_rub) for point in comparison.chart_data]
    if labels:
        positions = range(len(labels))
        width = 0.36
        axis.bar([position - width / 2 for position in positions], previous, width, label=comparison.previous_label, color="#94a3b8")
        axis.bar([position + width / 2 for position in positions], current, width, label=comparison.current_label, color="#2563eb")
        axis.set_xticks(list(positions), labels, rotation=30, ha="right")
    else:
        labels = [comparison.previous_label, comparison.current_label]
        totals = [float(comparison.previous_total_rub), float(comparison.current_total_rub)]
        axis.bar(labels, totals, color=["#94a3b8", "#2563eb"])
        for index, value in enumerate(totals):
            axis.text(index, value, f"{value:,.2f}", ha="center", va="bottom")
    axis.set_title("Expense comparison")
    axis.set_ylabel("RUB")
    axis.grid(axis="y", alpha=0.25)
    if comparison.chart_data:
        axis.legend()

    output = BytesIO()
    figure.savefig(output, format="png", dpi=150)
    plt.close(figure)
    metadata = {
        "filename": "expense-comparison.png",
        "mime_type": "image/png",
        "title": "Expense comparison",
    }
    return CallToolResult(
        content=[
            Image(data=output.getvalue(), format="png").to_image_content(),
            TextContent(type="text", text=json.dumps(metadata)),
        ],
        structured_content=metadata,
    )


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
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "8001")),
            streamable_http_path="/mcp",
        )
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
