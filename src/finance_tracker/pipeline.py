"""CLI pipeline coordinating the local MCP process and OpenAI SDK."""
from __future__ import annotations

from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
from typing import Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI

from .ai import Narrative, agent_search, classify_batch, fixed_transfer, generate_narrative, offline_classify
from .merchant_rules import rule_for_label
from .privacy import redact


LOG = logging.getLogger(__name__)


class ConfirmationDeclined(Exception):
    pass


def confirm_preview(path: str, generic_count: int, offline: bool) -> bool:
    print(f"Проверочный JSON сохранён: {path}", flush=True)
    print(f"Операций с обобщённым назначением: {generic_count}.", flush=True)
    if not offline:
        print("После подтверждения Markdown-файлы из knowledge/ будут отправлены в OpenAI для эмбеддингов без маскирования.", flush=True)
    try:
        answer = input("Проверьте JSON. Продолжить анализ? Введите «да»: ")
    except (EOFError, KeyboardInterrupt):
        print(flush=True)
        return False
    return answer.strip().casefold() == "да"


def progress(stage: str, percent: int, activity: str | None = None) -> None:
    print(f"{stage} ({percent}%)", flush=True)
    if activity:
        print(f" - {activity}", flush=True)


async def _tool(session: ClientSession, name: str, arguments: dict) -> object:
    result = await session.call_tool(name, arguments)
    if result.is_error:
        message = " ".join(block.text for block in result.content if getattr(block, "type", None) == "text")
        raise RuntimeError(message or f"Не удалось выполнить локальный инструмент: {name}")
    if result.structured_content is not None:
        content = result.structured_content
        # MCP servers may wrap primitive return values in a result field.
        if isinstance(content, dict) and set(content) == {"result"}:
            content = content["result"]
        if isinstance(content, dict) and "error" in content:
            raise RuntimeError(content["error"])
        return content
    for block in result.content:
        if getattr(block, "type", None) == "text":
            content = json.loads(block.text)
            if isinstance(content, dict) and "error" in content:
                raise RuntimeError(content["error"])
            return content
    raise RuntimeError(f"Локальный инструмент {name} вернул пустой ответ")


def _apply_classification(operation: dict, item) -> None:
    operation["flow"] = item.flow
    operation["category"] = item.category
    operation["uncertain"] = item.uncertain
    operation["classification_reason"] = item.reason
    operation["knowledge_sources"] = item.knowledge_sources


def _markdown(metrics: dict, narrative: Narrative, statements: list[dict], *, offline: bool) -> str:
    period = metrics["statement_period"]
    op_dates = metrics["operation_dates"]
    lines = [
        "# Анализ банковских выписок", "",
        ("Режим: без LLM, локальный полнотекстовый поиск по базе знаний." if offline else "Режим: OpenAI и семантический RAG по базе знаний."),
        "",
        f"Период выписок по дате обработки: **{period['start']} — {period['end']}** ({period['covered_days']} календарных дней покрытия).",
        f"Даты совершения операций: **{op_dates['start']} — {op_dates['end']}**.",
        "", "## Основные показатели", "",
        f"- Доходы без переводов себе: **{metrics['income']} ₽**",
        f"- Расходы без переводов себе: **{metrics['expense']} ₽**",
        f"- Разница доходов и расходов: **{metrics['net']} ₽**",
        f"- Переводы между своими счетами: входящие {metrics['transfers_in']} ₽, исходящие {metrics['transfers_out']} ₽",
        f"- Средние расходы: {metrics['average_expense_day']} ₽ в день, {metrics['average_expense_week']} ₽ в неделю покрытия",
        "", "## Основные категории расходов", "",
    ]
    lines += [f"- {item['name']}: {item['amount']} ₽" for item in metrics["top3_categories"]] or ["- Нет расходов."]
    lines += ["", "## Источники дохода", ""]
    lines += [f"- {item['name']}: {item['amount']} ₽" for item in metrics["income_categories"]] or ["- Нет поступлений, отнесённых к доходам."]
    lines += ["", "## Крупнейшие расходы", ""]
    lines += [f"- {item['date']}: {item['amount']} ₽ — {item['category']} ({item['description']})" for item in metrics["largest_expenses"]] or ["- Нет расходов."]
    lines += ["", "## Динамика по месяцам", "", "| Месяц | Дней покрытия | Доходы | Расходы | Расходы в день |", "| --- | ---: | ---: | ---: | ---: |"]
    lines += [f"| {item['month']} | {item['covered_days']} | {item['income']} ₽ | {item['expense']} ₽ | {item['average_expense_day']} ₽ |" for item in metrics["monthly"]]
    lines += ["", "## Динамика по неделям", "", "| Неделя | Дней покрытия | Расходы |", "| --- | ---: | ---: |"]
    lines += [f"| {item['week']} | {item['covered_days']} | {item['expense']} ₽ |" for item in metrics["weekly"]]
    if metrics["weekly_trend"]:
        trend = metrics["weekly_trend"]
        lines += ["", f"Сравнение первой и последней полных недель ({trend['first_week']} и {trend['last_week']}): {trend['direction']}, разница {trend['difference']} ₽."]
    else:
        lines += ["", "Полных недель для надёжного сравнения пока недостаточно."]
    lines += [
        "", "## Будни и выходные", "",
        f"- Будни: {metrics['weekday']['average_per_day']} ₽ за календарный день (дней: {metrics['weekday']['days']}).",
        f"- Выходные: {metrics['weekend']['average_per_day']} ₽ за календарный день (дней: {metrics['weekend']['days']}).",
        f"- Средний расход в выходной {metrics['weekend_behavior']} среднего расхода в будний день.",
        "", "## Наблюдения", "",
    ]
    lines += [f"- {item}" for item in narrative.observations] or ["- Наблюдений недостаточно."]
    lines += ["", "## Рекомендации", ""]
    lines += [f"- {item}" for item in narrative.recommendations] or ["- Дополните базу знаний финансовыми целями."]
    lines += ["", "## Качество данных", "", f"Операций: {metrics['operation_count']}; требуют проверки категории: {metrics['uncertain_operation_count']}."]
    if op_dates["start"] < period["start"] or op_dates["end"] > period["end"]:
        lines.append("Часть операций совершена вне периода выписки, но обработана банком в пределах периода. Для поведения по дням недели использована дата совершения.")
    lines += ["", "Банковские обороты ниже включают переводы между своими счетами:", ""]
    lines += [f"- {s['source_file']} ({'карта' if s.get('statement_type') == 'card' else 'счёт'} скрыт): поступления {s['bank_income']} ₽, списания {s['bank_expense']} ₽." for s in statements]
    if any(s.get("statement_type") == "card" for s in statements):
        lines.append("В выписке по карте есть операции в обработке; остатки по ней показаны справочно. Сверены суммы операций и банковские итоги, но равенство начального остатка, оборотов и конечного остатка для этого шаблона не применяется.")
    return "\n".join(lines)


async def run(paths: list[str], *, offline: bool = False, model: str = "gpt-4.1", embedding_model: str = "text-embedding-3-small", output_name: str | None = None, confirm: Callable[[str, int, bool], bool] | None = None) -> dict:
    if not paths:
        raise ValueError("Укажите хотя бы один PDF-файл")
    params = StdioServerParameters(command=sys.executable, args=["-m", "finance_tracker.mcp_server"], env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            progress("Парсинг банковских выписок", 0)
            statements = []
            for index, path in enumerate(paths, 1):
                statement = await _tool(session, "parse_pdf", {"path": str(Path(path).expanduser().resolve())})
                statements.append(statement)
                progress("Парсинг банковских выписок", round(index * 100 / len(paths)), f"Проверена выписка {index} из {len(paths)}")
            statements = list({s["source_id"]: s for s in statements}.values())
            operations = await _tool(session, "merge_operations", {"statements": statements})
            progress("Скрываю персональные данные", 0)
            name = output_name or datetime.now().strftime("analysis-%Y%m%d-%H%M%S")
            preview_payload = redact(statements, operations)
            saved_preview = await _tool(session, "write_redaction_preview", {"run_name": name, "payload": preview_payload})
            progress("Скрываю персональные данные", 100)
            approve = confirm or confirm_preview
            if not approve(saved_preview["path"], preview_payload["review"]["generic_description_count"], offline):
                raise ConfirmationDeclined(f"Анализ остановлен. Проверочный JSON сохранён: {saved_preview['path']}")
            approved_payload = await _tool(session, "read_redaction_preview", {"run_name": name, "expected_sha256": saved_preview["sha256"]})
            statements = approved_payload["statements"]
            operations = approved_payload["operations"]
            if not offline and not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("Не найден OPENAI_API_KEY. Добавьте его в .env или запустите с --offline")
            client = None if offline else OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=120)
            progress("Индексирую базу знаний", 0)
            rag_mode = "offline" if offline else "semantic"
            index_result = await _tool(session, "index_knowledge", {"mode": rag_mode, "embedding_model": embedding_model})
            LOG.info("Knowledge index: %s", index_result)
            progress("Индексирую базу знаний", 100)
            progress("Анализирую операции", 0)
            notes_by_id: dict[str, list[dict]] = {}
            rag_retrievals: list[dict] = []
            pending = []
            for operation in operations:
                if fixed_transfer(operation):
                    _apply_classification(operation, offline_classify(operation, []))
                    continue
                if offline:
                    query = operation["description"] + " " + operation["recipient"]
                    if "снятие наличных" in operation["description"].casefold():
                        query += " аренда квартира жильё наличные"
                    notes_by_id[operation["id"]] = await _tool(session, "search_knowledge", {"query": query, "limit": 3, "mode": "offline"})
                    rag_retrievals.append({"stage": "classification", "operation_ids": [operation["id"]], "query": query, "hits": [{"path": hit["path"], "score": None} for hit in notes_by_id[operation["id"]]]})
                pending.append(operation)
            batch_size = 12
            for start in range(0, len(pending), batch_size):
                batch = pending[start:start + batch_size]
                if offline:
                    classified = [offline_classify(op, notes_by_id[op["id"]]) for op in batch]
                else:
                    async def semantic_search(query: str, limit: int) -> list[dict]:
                        return await _tool(session, "search_knowledge", {"query": query, "limit": limit, "mode": "semantic", "embedding_model": embedding_model})

                    history, trace = await agent_search(
                        client, model, stage="classification",
                        payload=[{"id": op["id"], "amount": op["amount"], "description": op["description"], "recipient": op["recipient"]} for op in batch],
                        search=semantic_search, max_calls=4,
                        require_search=bool(index_result["chunks"]) and any(
                            "снятие наличных" in op["description"].casefold()
                            or (merchant_rule := rule_for_label(op["description"])) is not None and not merchant_rule["category"]
                            for op in batch
                        ),
                    )
                    for item in trace:
                        item["operation_ids"] = [op["id"] for op in batch]
                    rag_retrievals.extend(trace)
                    allowed = {hit["path"] for item in trace for hit in item["hits"]}
                    classified = classify_batch(client, model, batch, {}, history=history, allowed_sources=allowed)
                by_id = {item.id: item for item in classified}
                for operation in batch:
                    _apply_classification(operation, by_id[operation["id"]])
                progress("Анализирую операции", round(min(start + batch_size, len(pending)) * 80 / max(1, len(pending))), "Разбираю категории доходов и расходов")
            progress("Анализирую операции", 85, "Считаю показатели через локальный инструмент")
            metrics = await _tool(session, "calculate_metrics", {"operations": operations, "statements": statements})
            progress("Анализирую операции", 100)
            progress("Создаю отчёт", 0, "Формулирую наблюдения и рекомендации")
            if offline:
                narrative = Narrative(
                    observations=["Распределение расходов по категориям и датам приведено выше. Для уверенных выводов о долгосрочных трендах нужен более длительный период."],
                    recommendations=["Проверьте операции с неясной категорией и добавьте правила в базу знаний.", "Сравните основные категории расходов со своими финансовыми целями."],
                )
            else:
                async def report_search(query: str, limit: int) -> list[dict]:
                    return await _tool(session, "search_knowledge", {"query": query, "limit": limit, "mode": "semantic", "embedding_model": embedding_model})

                history, trace = await agent_search(
                    client, model, stage="reporting", payload={"metrics": metrics},
                    search=report_search, max_calls=3,
                )
                rag_retrievals.extend(trace)
                allowed = {hit["path"] for item in trace for hit in item["hits"]}
                narrative = generate_narrative(client, model, metrics, [], history=history, allowed_sources=allowed)
            progress("Создаю отчёт", 70, "Сохраняю JSON и Markdown")
            payload = {"schema_version": 3, "mode": "offline" if offline else "openai", "rag_mode": rag_mode, "redaction_review": approved_payload["review"], "rag_retrievals": rag_retrievals, "statements": statements, "operations": operations, "metrics": metrics, "narrative": narrative.model_dump()}
            markdown = _markdown(metrics, narrative, statements, offline=offline)
            saved = await _tool(session, "write_report", {"run_name": name, "payload": payload, "markdown": markdown})
            progress("Создаю отчёт", 100)
            return saved
