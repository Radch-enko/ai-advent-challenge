from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class ExpenseSearchFilters(BaseModel):
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

    @field_validator("occurred_from", "occurred_to")
    @classmethod
    def require_filter_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("date filters must include a timezone offset")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_filter_tags(cls, value: list[str]) -> list[str]:
        normalized = [tag.strip() for tag in value]
        if any(not tag for tag in normalized):
            raise ValueError("tags must not contain empty values")
        return normalized

    @model_validator(mode="after")
    def validate_ranges(self) -> ExpenseSearchFilters:
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
