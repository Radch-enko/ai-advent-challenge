"""Local stdio MCP server. No financial arithmetic is performed by the LLM."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from hashlib import sha256
from math import sqrt
from pathlib import Path
import json
import logging
import os
import re
import sqlite3
import tempfile

from mcp.server.mcpserver import MCPServer
from openai import OpenAI, OpenAIError

from .parser import merge_statements, parse_statement
from .parser import StatementError
from .privacy import validate_preview


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "knowledge"
INDEX = ROOT / "data" / "knowledge.sqlite3"
OUTPUT = ROOT / "output"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_QUERY_VECTORS: dict[tuple[str, str], list[float]] = {}
server = MCPServer("finance-files-and-math", instructions="Local statement files, knowledge search and exact financial calculations.")
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(filename=LOG_DIR / "mcp.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)
LOG = logging.getLogger(__name__)


def safe_tool(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (StatementError, ValueError) as exc:
            LOG.exception("MCP tool failed: %s", fn.__name__)
            return {"error": str(exc)}
        except OpenAIError:
            LOG.exception("Embedding API failed in MCP tool: %s", fn.__name__)
            return {"error": "Не удалось получить эмбеддинги OpenAI. Проверьте ключ, сеть и доступ к модели эмбеддингов"}
        except Exception:
            LOG.exception("MCP tool failed: %s", fn.__name__)
            return {"error": "Локальная обработка завершилась ошибкой; подробности в logs/mcp.log"}
    return wrapped


def _rub(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _safe_inside(path: Path, base: Path) -> bool:
    return path.resolve().is_relative_to(base.resolve())


def _chunks() -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    for path in sorted(KNOWLEDGE.rglob("*.md")):
        if not _safe_inside(path, KNOWLEDGE):
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")) if p.strip()]
        chunk = ""
        for paragraph in paragraphs:
            # Long paragraphs also need bounded chunks for the embedding endpoint.
            pieces = [paragraph[i:i + 1200] for i in range(0, len(paragraph), 1200)]
            for piece in pieces:
                if len(chunk) + len(piece) > 1200 and chunk:
                    relative = str(path.relative_to(KNOWLEDGE))
                    result.append((sha256(f"{relative}\0{chunk}".encode()).hexdigest(), relative, chunk))
                    chunk = ""
                chunk = f"{chunk}\n\n{piece}".strip()
        if chunk:
            relative = str(path.relative_to(KNOWLEDGE))
            result.append((sha256(f"{relative}\0{chunk}".encode()).hexdigest(), relative, chunk))
    return result


def _embed_texts(texts: list[str], model: str) -> list[list[float]]:
    if not texts:
        return []
    response = OpenAI(timeout=120).embeddings.create(model=model, input=texts)
    return [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("Размерность эмбеддингов в индексе не совпадает с запросом")
    denominator = sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / denominator if denominator else 0.0


@server.tool(description="Read and validate a supported local PDF statement, preserving source row positions.")
@safe_tool
def parse_pdf(path: str) -> dict:
    return parse_statement(path)


@server.tool(description="Merge overlapping statement files without removing legitimate repeated purchases.")
@safe_tool
def merge_operations(statements: list[dict]) -> list[dict]:
    return merge_statements(statements)


@server.tool(description="Index local Markdown notes after the user approves the redacted statement preview; semantic mode caches OpenAI embeddings.")
@safe_tool
def index_knowledge(mode: str = "semantic", embedding_model: str = DEFAULT_EMBEDDING_MODEL) -> dict:
    if mode not in {"semantic", "offline"}:
        raise ValueError("Неизвестный режим индексации")
    KNOWLEDGE.mkdir(exist_ok=True)
    INDEX.parent.mkdir(exist_ok=True)
    chunks = _chunks()
    with sqlite3.connect(INDEX) as db:
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(path UNINDEXED, body, tokenize='unicode61')")
        db.execute("CREATE TABLE IF NOT EXISTS vectors (hash TEXT PRIMARY KEY, path TEXT NOT NULL, body TEXT NOT NULL, model TEXT NOT NULL, embedding TEXT NOT NULL)")
        db.execute("DELETE FROM chunks")
        db.executemany("INSERT INTO chunks(path, body) VALUES (?, ?)", [(path, body) for _, path, body in chunks])
        db.commit()
        reused = 0
        if mode == "semantic":
            existing = {row[0] for row in db.execute("SELECT hash FROM vectors WHERE model = ?", (embedding_model,))}
            missing = [(digest, path, body) for digest, path, body in chunks if digest not in existing]
            reused = len(chunks) - len(missing)
            for start in range(0, len(missing), 32):
                batch = missing[start:start + 32]
                vectors = _embed_texts([body for _, _, body in batch], embedding_model)
                if len(vectors) != len(batch):
                    raise ValueError("API вернул неполный набор эмбеддингов")
                db.executemany(
                    "INSERT OR REPLACE INTO vectors(hash, path, body, model, embedding) VALUES (?, ?, ?, ?, ?)",
                    [(digest, path, body, embedding_model, json.dumps(vector)) for (digest, path, body), vector in zip(batch, vectors)],
                )
            current = {digest for digest, _, _ in chunks}
            for (digest,) in db.execute("SELECT hash FROM vectors"):
                if digest not in current:
                    db.execute("DELETE FROM vectors WHERE hash = ?", (digest,))
            db.commit()
    return {"files": len({path for _, path, _ in chunks}), "chunks": len(chunks), "cached_vectors": reused, "mode": mode}


@server.tool(description="Retrieve relevant financial notes by semantic vector similarity or offline FTS5.")
@safe_tool
def search_knowledge(query: str, limit: int = 3, mode: str = "semantic", embedding_model: str = DEFAULT_EMBEDDING_MODEL) -> list[dict]:
    if not INDEX.exists():
        return []
    if mode not in {"semantic", "offline"}:
        raise ValueError("Неизвестный режим поиска")
    if not query.strip():
        return []
    if mode == "semantic":
        with sqlite3.connect(INDEX) as db:
            rows = db.execute("SELECT path, body, embedding FROM vectors WHERE model = ?", (embedding_model,)).fetchall()
        if not rows:
            return []
        key = (embedding_model, query)
        if key not in _QUERY_VECTORS:
            _QUERY_VECTORS[key] = _embed_texts([query], embedding_model)[0]
        query_vector = _QUERY_VECTORS[key]
        ranked = sorted(
            ((path, body, _cosine(query_vector, json.loads(vector))) for path, body, vector in rows),
            key=lambda item: item[2], reverse=True,
        )
        return [{"path": path, "text": body[:1200], "score": round(score, 4)} for path, body, score in ranked[:max(1, min(limit, 10))]]
    terms = re.findall(r"[\wА-Яа-яЁё]{3,}", query.lower())[:12]
    if not terms:
        return []
    expression = " OR ".join('"' + t.replace('"', '') + '"' for t in terms)
    with sqlite3.connect(INDEX) as db:
        rows = db.execute(
            "SELECT path, body FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?",
            (expression, max(1, min(limit, 10))),
        ).fetchall()
    return [{"path": path, "text": body[:1200]} for path, body in rows]


@server.tool(description="Calculate all financial totals and time statistics exactly using Decimal.")
@safe_tool
def calculate_metrics(operations: list[dict], statements: list[dict]) -> dict:
    if not operations or not statements:
        raise ValueError("Для расчёта нужны операции и выписки")
    income = expense = transfers_in = transfers_out = Decimal(0)
    categories: dict[str, Decimal] = defaultdict(Decimal)
    income_categories: dict[str, Decimal] = defaultdict(Decimal)
    months: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"income": Decimal(0), "expense": Decimal(0)})
    weeks: dict[str, Decimal] = defaultdict(Decimal)
    weekday_spend = weekend_spend = Decimal(0)
    biggest: list[dict] = []
    uncertain: list[str] = []
    for op in operations:
        amount = Decimal(op["amount"])
        flow = op.get("flow", "expense" if amount < 0 else "income")
        if op.get("uncertain"):
            uncertain.append(op["id"])
        if flow == "transfer":
            if amount >= 0:
                transfers_in += amount
            else:
                transfers_out += -amount
            continue
        month = op["processing_date"][:7]
        if flow == "income":
            if amount < 0:
                raise ValueError("Доход не может быть списанием")
            income += amount
            months[month]["income"] += amount
            income_categories[op.get("category") or "Прочие поступления"] += amount
        elif flow == "expense":
            if amount > 0:
                raise ValueError("Расход не может быть зачислением")
            value = -amount
            expense += value
            months[month]["expense"] += value
            processed = date.fromisoformat(op["processing_date"])
            week = processed.isocalendar()
            weeks[f"{week.year}-W{week.week:02d}"] += value
            categories[op.get("category") or "Не определено"] += value
            biggest.append({"id": op["id"], "date": op["operation_date"], "amount": _rub(value), "category": op.get("category") or "Не определено", "description": op["description"][:160]})
            if date.fromisoformat(op["operation_date"]).weekday() >= 5:
                weekend_spend += value
            else:
                weekday_spend += value
        else:
            raise ValueError(f"Неизвестный тип операции: {flow}")
    covered: set[date] = set()
    for statement in statements:
        current = date.fromisoformat(statement["period_start"])
        end = date.fromisoformat(statement["period_end"])
        while current <= end:
            covered.add(current)
            current += timedelta(days=1)
    if not covered:
        raise ValueError("Не удалось определить период покрытия")
    days = len(covered)
    operative_start = min(o["operation_date"] for o in operations)
    operative_end = max(o["operation_date"] for o in operations)
    operative_days: set[date] = set()
    current = date.fromisoformat(operative_start)
    end = date.fromisoformat(operative_end)
    while current <= end:
        operative_days.add(current)
        current += timedelta(days=1)
    weekend_days = sum(day.weekday() >= 5 for day in operative_days)
    weekday_days = len(operative_days) - weekend_days
    top_categories = sorted(categories.items(), key=lambda item: (-item[1], item[0]))
    top_income = sorted(income_categories.items(), key=lambda item: (-item[1], item[0]))
    biggest.sort(key=lambda item: (-Decimal(item["amount"]), item["date"], item["id"]))
    month_days: dict[str, int] = defaultdict(int)
    week_days: dict[str, int] = defaultdict(int)
    for day in covered:
        month_days[day.strftime("%Y-%m")] += 1
        iso = day.isocalendar()
        week_days[f"{iso.year}-W{iso.week:02d}"] += 1
    complete_weeks = [(week, weeks[week]) for week in sorted(week_days) if week_days[week] == 7]
    weekly_trend = None
    if len(complete_weeks) >= 2:
        first_week, first_amount = complete_weeks[0]
        last_week, last_amount = complete_weeks[-1]
        difference = last_amount - first_amount
        weekly_trend = {
            "first_week": first_week, "last_week": last_week,
            "first_expense": _rub(first_amount), "last_expense": _rub(last_amount),
            "difference": _rub(difference),
            "direction": "рост" if difference > 0 else "снижение" if difference < 0 else "без изменений",
        }
    weekday_average = weekday_spend / weekday_days if weekday_days else Decimal(0)
    weekend_average = weekend_spend / weekend_days if weekend_days else Decimal(0)
    return {
        "statement_period": {"start": min(s["period_start"] for s in statements), "end": max(s["period_end"] for s in statements), "covered_days": days},
        "operation_dates": {"start": operative_start, "end": operative_end},
        "bank_totals_by_statement": [{"source_file": s["source_file"], "income": s["bank_income"], "expense": s["bank_expense"], "opening_balance": s["opening_balance"], "closing_balance": s["closing_balance"]} for s in statements],
        "income": _rub(income), "expense": _rub(expense), "net": _rub(income - expense),
        "transfers_in": _rub(transfers_in), "transfers_out": _rub(transfers_out),
        "average_expense_day": _rub(expense / days),
        "average_expense_week": _rub(expense * 7 / days),
        "categories": [{"name": name, "amount": _rub(value)} for name, value in top_categories],
        "top3_categories": [{"name": name, "amount": _rub(value)} for name, value in top_categories[:3]],
        "income_categories": [{"name": name, "amount": _rub(value)} for name, value in top_income],
        "largest_expenses": biggest[:5],
        "monthly": [{"month": month, "income": _rub(months[month]["income"]), "expense": _rub(months[month]["expense"]), "covered_days": month_days[month], "average_expense_day": _rub(months[month]["expense"] / month_days[month])} for month in sorted(month_days)],
        "weekly": [{"week": week, "expense": _rub(weeks[week]), "covered_days": week_days[week]} for week in sorted(week_days)],
        "weekly_trend": weekly_trend,
        "weekend": {"total": _rub(weekend_spend), "days": weekend_days, "average_per_day": _rub(weekend_average)},
        "weekday": {"total": _rub(weekday_spend), "days": weekday_days, "average_per_day": _rub(weekday_average)},
        "weekend_behavior": "выше" if weekend_average > weekday_average else "ниже" if weekend_average < weekday_average else "на одном уровне",
        "uncertain_operation_ids": uncertain,
        "uncertain_operation_count": len(uncertain),
        "operation_count": len(operations),
    }


@server.tool(description="Save JSON and Markdown analysis in the project's private output directory.")
@safe_tool
def write_report(run_name: str, payload: dict, markdown: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_name):
        raise ValueError("Некорректное имя результата")
    OUTPUT.mkdir(exist_ok=True)
    json_path = OUTPUT / f"{run_name}.json"
    md_path = OUTPUT / f"{run_name}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


@server.tool(description="Save a redacted statement preview locally for explicit user approval.")
@safe_tool
def write_redaction_preview(run_name: str, payload: dict) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_name):
        raise ValueError("Некорректное имя результата")
    validate_preview(payload)
    OUTPUT.mkdir(exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path = OUTPUT / f"{run_name}.preview.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=OUTPUT, prefix=".preview-", delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": str(path), "sha256": sha256(data).hexdigest()}


@server.tool(description="Read only an unchanged, validated redacted preview after user approval.")
@safe_tool
def read_redaction_preview(run_name: str, expected_sha256: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_name):
        raise ValueError("Некорректное имя результата")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Некорректная контрольная сумма проверочного JSON")
    path = OUTPUT / f"{run_name}.preview.json"
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError("Не удалось повторно открыть проверочный JSON") from exc
    if sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Проверочный JSON изменён после сохранения. Запустите анализ заново")
    try:
        return validate_preview(json.loads(data))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Проверочный JSON повреждён") from exc


if __name__ == "__main__":
    server.run(transport="stdio")
