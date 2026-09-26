from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

MONTHS_RU = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
ISO_DATETIME = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b")


def human_datetime(value: datetime, timezone: str) -> str:
    local = value.astimezone(ZoneInfo(timezone))
    return f"{local.day} {MONTHS_RU[local.month - 1]} {local.year} года, {local:%H:%M}"


def humanize_report_datetimes(answer: str, timezone: str) -> str:
    def replace(match: re.Match[str]) -> str:
        try:
            parsed = datetime.fromisoformat(match.group(0).replace("Z", "+00:00"))
        except ValueError:
            return match.group(0)
        return human_datetime(parsed, timezone)

    return ISO_DATETIME.sub(replace, answer)
