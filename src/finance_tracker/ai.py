"""OpenAI classification and qualitative commentary; no monetary calculations."""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Awaitable, Callable, Literal

from openai import OpenAI
from pydantic import BaseModel

from .merchant_rules import rule_for_label


LOG = logging.getLogger(__name__)


class ClassifiedItem(BaseModel):
    id: str
    flow: Literal["income", "expense", "transfer"]
    category: str
    uncertain: bool
    reason: str
    knowledge_sources: list[str] = []


class ClassificationBatch(BaseModel):
    items: list[ClassifiedItem]


class Narrative(BaseModel):
    observations: list[str]
    recommendations: list[str]
    knowledge_sources: list[str] = []


SEARCH_TOOL = {
    "type": "function",
    "name": "search_knowledge",
    "description": "Semantic search in the user's private financial goals and classification notes. Formulate a focused natural-language query when an operation or report conclusion needs context not present in the statement.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Your own focused question or description for semantic retrieval."},
            "limit": {"type": "integer", "description": "Number of relevant note fragments, from 1 to 5."},
        },
        "required": ["query", "limit"],
        "additionalProperties": False,
    },
    "strict": True,
}


async def agent_search(
    client: OpenAI,
    model: str,
    *,
    stage: str,
    payload: dict | list,
    search: Callable[[str, int], Awaitable[list[dict]]],
    max_calls: int,
    require_search: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Let the model request retrieval through a Responses function bridged to MCP."""
    instructions = (
        "Ты анализируешь операции" if stage == "classification" else "Ты готовишь финансовый отчёт"
    ) + (
        ". Если значение операции неоднозначно, сам сформулируй запрос к search_knowledge "
        "перед окончательной классификацией. Не ищи по каждой очевидной операции. "
        "Не угадывай назначение наличных или общего названия продавца."
        if stage == "classification" else
        ". При необходимости сам сформулируй запрос к search_knowledge о целях, правилах "
        "и обстоятельствах пользователя, опираясь на готовые показатели. Не вычисляй показатели."
    ) + " Когда поиск закончен или не нужен, ответь кратко: готово."
    history: list[dict] = [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    trace: list[dict] = []
    used = 0
    while used < max_calls:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=history,
            tools=[SEARCH_TOOL],
            tool_choice="required" if require_search and used == 0 else "auto",
            parallel_tool_calls=False,
            store=False,
            timeout=120,
        )
        LOG.info("OpenAI retrieval decision: stage=%s request_id=%s", stage, getattr(response, "_request_id", None))
        history.extend(item.model_dump(exclude_none=True) for item in response.output)
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            break
        for call in calls:
            used += 1
            try:
                args = json.loads(call.arguments)
                query = str(args["query"]).strip()[:500]
                limit = max(1, min(int(args["limit"]), 5))
                if call.name != "search_knowledge" or not query:
                    raise ValueError("Некорректный запрос к базе знаний")
                if used <= max_calls:
                    hits = await search(query, limit)
                    trace.append({
                        "stage": stage, "query": query,
                        "hits": [{"path": hit["path"], "score": hit.get("score")} for hit in hits],
                    })
                    output = hits
                else:
                    output = {"error": "Достигнут предел поисковых запросов"}
            except (KeyError, ValueError, TypeError) as exc:
                output = {"error": str(exc)}
            history.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(output, ensure_ascii=False)})
        if used >= max_calls:
            break
    return history, trace


def fixed_transfer(operation: dict) -> bool:
    description = operation["description"].casefold()
    return "перевод между своими счетами" in description or (
        operation.get("is_self_recipient", False) and "перевод" in description
    )


def offline_classify(operation: dict, notes: list[dict]) -> ClassifiedItem:
    description = operation["description"].casefold()
    amount = Decimal(operation["amount"])
    if fixed_transfer(operation):
        return ClassifiedItem(id=operation["id"], flow="transfer", category="Перевод между своими счетами", uncertain=False, reason="Прямое указание в выписке")
    if amount > 0:
        if "заработная плата" in description or "аванс по трудовому" in description:
            category, uncertain = "Зарплата", False
        elif "кешбэк" in description:
            category, uncertain = "Кешбэк", False
        else:
            category, uncertain = "Прочие поступления", True
        return ClassifiedItem(id=operation["id"], flow="income", category=category, uncertain=uncertain, reason="Правило локального режима")
    if "снятие наличных" in description:
        for note in notes:
            lower = note["text"].casefold()
            if "снятие наличных" in lower and ("квартир" in lower or "аренд" in lower):
                return ClassifiedItem(id=operation["id"], flow="expense", category="Жильё", uncertain=False, reason=f"Правило базы знаний: {note['path']}", knowledge_sources=[note["path"]])
        return ClassifiedItem(id=operation["id"], flow="expense", category="Наличные без назначения", uncertain=True, reason="Назначение снятия неизвестно")
    merchant_rule = rule_for_label(operation["description"])
    if merchant_rule and merchant_rule["category"]:
        return ClassifiedItem(id=operation["id"], flow="expense", category=merchant_rule["category"], uncertain=False, reason="Локальное правило продавца")
    rules = [
        (("подписк",), "Подписки"),
        (("налог",), "Налоги"),
    ]
    for keys, category in rules:
        if any(key in description for key in keys):
            return ClassifiedItem(id=operation["id"], flow="expense", category=category, uncertain=False, reason="Правило локального режима")
    return ClassifiedItem(id=operation["id"], flow="expense", category="Не определено", uncertain=True, reason="Недостаточно данных для классификации")


def classify_batch(client: OpenAI, model: str, operations: list[dict], notes_by_id: dict[str, list[dict]], *, history: list[dict] | None = None, allowed_sources: set[str] | None = None) -> list[ClassifiedItem]:
    payload = [{
        "id": op["id"], "amount": op["amount"], "description": op["description"],
        "recipient": op["recipient"], "knowledge": notes_by_id.get(op["id"], []),
    } for op in operations]
    response = client.responses.parse(
        model=model,
        instructions=(
            "Классифицируй банковские операции на русском. Не вычисляй суммы и статистику. "
            "Строго сохрани id. Положительная сумма — income, отрицательная — expense, "
            "кроме переводов между своими счетами (transfer). Категорию определяй по тексту "
            "и базе знаний. Наличные без подтверждённого назначения и общее название продавца "
            "помечай uncertain=true и не угадывай точный вид покупки. "
            "Верни ровно одну запись на каждую входную операцию. В knowledge_sources "
            "укажи только пути действительно использованных заметок из результатов поиска; "
            "если заметка нерелевантна, не опирайся на неё и оставь uncertain=true."
        ),
        input=history if history is not None else json.dumps(payload, ensure_ascii=False),
        text_format=ClassificationBatch,
        store=False,
        timeout=120,
    )
    LOG.info("OpenAI classification request completed: request_id=%s", getattr(response, "_request_id", None))
    result = response.output_parsed
    if result is None:
        raise RuntimeError("AI не вернул структурированную классификацию")
    expected = {op["id"] for op in operations}
    found = [item.id for item in result.items]
    if set(found) != expected or len(found) != len(expected):
        raise RuntimeError("AI пропустил или повторил операции при классификации")
    for item in result.items:
        if item.flow not in {"income", "expense", "transfer"}:
            raise RuntimeError(f"AI вернул неизвестный тип операции: {item.flow}")
        op = next(op for op in operations if op["id"] == item.id)
        if fixed_transfer(op):
            item.flow = "transfer"
            item.category = "Перевод между своими счетами"
            item.uncertain = False
        elif item.flow == "transfer":
            item.flow = "income" if Decimal(op["amount"]) > 0 else "expense"
            item.uncertain = True
        elif (Decimal(op["amount"]) > 0 and item.flow == "expense") or (Decimal(op["amount"]) < 0 and item.flow == "income"):
            raise RuntimeError("AI перепутал направление операции")
        if op.get("description_hidden") and item.flow != "transfer":
            item.category = "Прочие поступления" if item.flow == "income" else "Не определено"
            item.uncertain = True
        if allowed_sources is not None:
            invalid = set(item.knowledge_sources) - allowed_sources
            if invalid:
                item.uncertain = True
                item.knowledge_sources = [path for path in item.knowledge_sources if path in allowed_sources]
            description = op["description"].casefold()
            if not item.knowledge_sources and "снятие наличных" in description:
                item.category = "Наличные без назначения"
                item.uncertain = True
            elif not item.knowledge_sources and (merchant_rule := rule_for_label(op["description"])) and not merchant_rule["category"]:
                item.category = "Не определено"
                item.uncertain = True
    return result.items


def generate_narrative(client: OpenAI, model: str, metrics: dict, notes: list[dict], *, history: list[dict] | None = None, allowed_sources: set[str] | None = None) -> Narrative:
    response = client.responses.parse(
        model=model,
        instructions=(
            "Напиши краткие наблюдения и практичные рекомендации по финансам на русском. "
            "Используй только предоставленные статистические показатели и заметки. "
            "Не выполняй вычисления, не вводи новых чисел, процентов или неподтверждённых причин. "
            "Если данных мало для тренда, явно скажи об этом. Не выдавай финансовые советы как гарантию. "
            "В knowledge_sources укажи только пути реально использованных заметок из результатов поиска."
        ),
        input=history if history is not None else json.dumps({"metrics": metrics, "knowledge": notes}, ensure_ascii=False),
        text_format=Narrative,
        store=False,
        timeout=120,
    )
    LOG.info("OpenAI report request completed: request_id=%s", getattr(response, "_request_id", None))
    if response.output_parsed is None:
        raise RuntimeError("AI не вернул текстовые выводы")
    narrative = response.output_parsed
    if allowed_sources is not None:
        narrative.knowledge_sources = [path for path in narrative.knowledge_sources if path in allowed_sources]
    return narrative
