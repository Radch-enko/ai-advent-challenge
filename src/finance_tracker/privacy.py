"""Conservative, local redaction before any statement data reaches OpenAI."""
from __future__ import annotations

from decimal import Decimal

from .merchant_rules import label_for_description


HIDDEN_PURPOSE = "Назначение скрыто"


def _description(operation: dict) -> str:
    raw = " ".join(operation["description"].casefold().split())
    if "перевод между своими счетами" in raw or (operation.get("is_self_recipient") and "перевод" in raw):
        return "Перевод между своими счетами"
    if "заработная плата" in raw or "аванс по трудовому" in raw:
        return "Заработная плата"
    if "кешбэк" in raw or "кэшбэк" in raw:
        return "Кешбэк"
    if "снятие наличных" in raw:
        return "Снятие наличных"
    if "внесение наличных" in raw:
        return "Внесение наличных"
    if "оплата товаров и услуг" in raw:
        # Emit only configured labels. Free-form source text may contain names,
        # account numbers, phone numbers or payment notes after the merchant.
        label = label_for_description(raw)
        if label:
            return label
    return HIDDEN_PURPOSE


def redact(statements: list[dict], operations: list[dict]) -> dict:
    """Return a strict allowlist-shaped payload; never copy source text wholesale."""
    source_aliases = {s["source_id"]: f"statement-{index}" for index, s in enumerate(statements, 1)}
    account_aliases = {account_id: f"account-{index}" for index, account_id in enumerate(dict.fromkeys(s["account_id"] for s in statements), 1)}
    clean_statements: list[dict] = []
    for statement in statements:
        source = source_aliases[statement["source_id"]]
        clean = {
            "source_id": source,
            "source_file": f"Выписка {source.split('-')[1]}",
            "account_id": account_aliases[statement["account_id"]],
            "account_last4": "скрыто",
            "statement_type": statement.get("statement_type", "account"),
            "balance_check": statement.get("balance_check", "reconciled"),
            "period_start": statement["period_start"],
            "period_end": statement["period_end"],
            "opening_balance": statement["opening_balance"],
            "closing_balance": statement["closing_balance"],
            "bank_income": statement["bank_income"],
            "bank_expense": statement["bank_expense"],
        }
        for optional in ("bank_commission", "pending_amount"):
            if optional in statement:
                clean[optional] = statement[optional]
        clean_statements.append(clean)
    clean_operations: list[dict] = []
    generic_count = 0
    for index, operation in enumerate(operations, 1):
        source = source_aliases[operation["source_id"]]
        description = _description(operation)
        generic_count += description == HIDDEN_PURPOSE
        amount = Decimal(operation["amount"])
        clean = {
            "id": f"operation-{index}",
            "source_id": source,
            "source_file": f"Выписка {source.split('-')[1]}",
            "account_id": account_aliases[operation["account_id"]],
            "page": operation["page"],
            "row": operation["row"],
            "operation_date": operation["operation_date"],
            "processing_date": operation["processing_date"],
            "amount": operation["amount"],
            "credit": operation["credit"],
            "debit": operation["debit"],
            "direction": "income" if amount > 0 else "expense" if amount < 0 else "zero",
            "description": description,
            "recipient": "",
            "is_self_recipient": bool(operation.get("is_self_recipient", False)),
            "description_hidden": description == HIDDEN_PURPOSE,
        }
        if "operation_time" in operation:
            clean["operation_time"] = operation["operation_time"]
        clean_operations.append(clean)
    return {
        "schema_version": 1,
        "statements": clean_statements,
        "operations": clean_operations,
        "review": {"operation_count": len(clean_operations), "generic_description_count": generic_count},
    }


def validate_preview(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "statements", "operations", "review"}:
        raise ValueError("Проверочный JSON имеет неверную структуру")
    if payload["schema_version"] != 1 or not isinstance(payload["statements"], list) or not isinstance(payload["operations"], list):
        raise ValueError("Проверочный JSON имеет неверную структуру")
    statement_keys = {"source_id", "source_file", "account_id", "account_last4", "statement_type", "balance_check", "period_start", "period_end", "opening_balance", "closing_balance", "bank_income", "bank_expense"}
    operation_keys = {"id", "source_id", "source_file", "account_id", "page", "row", "operation_date", "processing_date", "amount", "credit", "debit", "direction", "description", "recipient", "is_self_recipient", "description_hidden"}
    if any(not isinstance(s, dict) or not statement_keys <= set(s) or set(s) - statement_keys - {"bank_commission", "pending_amount"} for s in payload["statements"]):
        raise ValueError("Проверочный JSON содержит неожиданные поля выписки")
    if any(not isinstance(op, dict) or not operation_keys <= set(op) or set(op) - operation_keys - {"operation_time"} for op in payload["operations"]):
        raise ValueError("Проверочный JSON содержит неожиданные поля операции")
    review = payload["review"]
    if not isinstance(review, dict) or set(review) != {"operation_count", "generic_description_count"} or review["operation_count"] != len(payload["operations"]):
        raise ValueError("Проверочный JSON имеет неверные показатели проверки")
    return payload
