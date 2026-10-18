"""Optional local merchant hints; the rule file is excluded from Git."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path


RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "merchant_rules.json"


@lru_cache(maxsize=1)
def rules() -> tuple[dict, ...]:
    if not RULES_PATH.exists():
        return ()
    try:
        value = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Не удалось прочитать локальные правила продавцов") from exc
    if not isinstance(value, list) or any(
        not isinstance(item, dict)
        or set(item) != {"marker", "label", "category"}
        or not isinstance(item["marker"], str)
        or not item["marker"].strip()
        or not isinstance(item["label"], str)
        or not item["label"].strip()
        or (item["category"] is not None and not isinstance(item["category"], str))
        for item in value
    ):
        raise ValueError("Некорректный формат локальных правил продавцов")
    return tuple(value)


def label_for_description(raw: str) -> str | None:
    for item in rules():
        if item["marker"].casefold() in raw.casefold():
            return item["label"]
    return None


def rule_for_label(label: str) -> dict | None:
    return next((item for item in rules() if item["label"] == label), None)
