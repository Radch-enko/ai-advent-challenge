from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
