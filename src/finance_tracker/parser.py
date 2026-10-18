"""Coordinate-based adapters for supported account and card statement PDFs."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import re

import pdfplumber


class StatementError(ValueError):
    pass


DATE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
MONEY = re.compile(r"^(-?\d+(?:[.,]\d{1,2})?)\s*RUB$")
PERIOD = re.compile(r"Период выписки\s+(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})")
ACCOUNT = re.compile(r"Номер сч[её]та\s+(\d+)\s*\(RUB\)")
CARD = re.compile(r"Номер карты\s+(\d{4})\b")
CARD_AMOUNT = re.compile(r"^(-?\d+(?:[.,]\d{1,2})?)$")
TIME = re.compile(r"^\d{2}:\d{2}:\d{2}$")


def _date(value: str) -> str:
    try:
        return datetime.strptime(value, "%d.%m.%Y").date().isoformat()
    except ValueError as exc:
        raise StatementError(f"Некорректная дата в выписке: {value}") from exc


def _money(value: str) -> Decimal:
    match = MONEY.match(" ".join(value.split()))
    if not match:
        raise StatementError(f"Не удалось прочитать сумму: {value!r}")
    try:
        return Decimal(match.group(1).replace(",", "."))
    except InvalidOperation as exc:
        raise StatementError(f"Некорректная сумма: {value!r}") from exc


def _cell(page, left: float, right: float, top: float, bottom: float) -> str:
    text = page.crop((left + 1, top + 1, right - 1, bottom - 1)).extract_text(
        x_tolerance=2, y_tolerance=2
    )
    return " ".join((text or "").split())


def _boundaries(page, first_column_right: float = 80) -> list[float]:
    # The first table column has a horizontal border at every transaction edge.
    return sorted({
        round(line["top"], 1)
        for line in page.lines
        if 18.5 <= line["x0"] <= 21.5
        and first_column_right - 1.5 <= line["x1"] <= first_column_right + 1.5
        and abs(line["top"] - line["bottom"]) < 0.2
    })


def _header_amount(text: str, label: str) -> Decimal:
    match = re.search(re.escape(label) + r"\s+(-?\d+[.,]\d{1,2})\s*RUB", text)
    if not match:
        raise StatementError(f"Не найден итог банка: {label}")
    return Decimal(match.group(1).replace(",", "."))


def _card_money(value: str) -> Decimal:
    match = CARD_AMOUNT.fullmatch(" ".join(value.split()))
    if not match:
        raise StatementError(f"Не удалось прочитать сумму в валюте карты: {value!r}")
    return Decimal(match.group(1).replace(",", ".")).quantize(Decimal("0.01"))


def _parse_account(pdf, pdf_path: Path, first: str, period_start: str, period_end: str, source_id: str) -> dict:
    account = ACCOUNT.search(first)
    if not account:
        raise StatementError("В выписке по счёту не найден номер счёта")
    opening = _header_amount(first, "Баланс на начало периода")
    closing = _header_amount(first, "Баланс на конец периода")
    bank_income = _header_amount(first, "Поступления")
    bank_expense = _header_amount(first, "Расходные операции")
    account_number = account.group(1)
    owner_name = first.split("Номер счёта", 1)[0].strip().splitlines()[-1].strip()
    account_id = sha256(account_number.encode()).hexdigest()[:16]
    operations: list[dict] = []
    for page_number, page in enumerate(pdf.pages, 1):
        edges = _boundaries(page)
        for row_number, (top, bottom) in enumerate(zip(edges, edges[1:]), 1):
            operation_date = _cell(page, 20, 80, top, bottom)
            if not DATE.fullmatch(operation_date):
                continue
            processed = _cell(page, 80, 150, top, bottom)
            if not DATE.fullmatch(processed):
                raise StatementError(f"Страница {page_number}: нет даты обработки у операции")
            amount = _money(_cell(page, 150, 230, top, bottom))
            credit = _money(_cell(page, 230, 310, top, bottom))
            debit = _money(_cell(page, 310, 390, top, bottom))
            if amount != credit + debit or credit < 0 or debit > 0:
                raise StatementError(f"Страница {page_number}: суммы операции противоречат друг другу")
            processing_date = _date(processed)
            if not period_start <= processing_date <= period_end:
                raise StatementError(f"Страница {page_number}: дата обработки вне периода выписки")
            description = _cell(page, 390, 500, top, bottom)
            recipient = _cell(page, 500, 574, top, bottom)
            is_self_recipient = bool(recipient) and " ".join(recipient.casefold().split()) == " ".join(owner_name.casefold().split())
            if not description and not recipient:
                raise StatementError(f"Страница {page_number}: пустое описание операции")
            operations.append({
                "id": f"{source_id[:12]}-{page_number}-{row_number}",
                "source_id": source_id, "source_file": pdf_path.name,
                "page": page_number, "row": row_number, "account_id": account_id,
                "operation_date": _date(operation_date), "processing_date": processing_date,
                "amount": str(amount), "credit": str(credit), "debit": str(debit),
                "description": description, "recipient": recipient,
                "is_self_recipient": is_self_recipient,
            })
    if opening + bank_income - bank_expense != closing:
        raise StatementError("Начальный баланс и обороты не сходятся с конечным балансом")
    return {
        "source_id": source_id, "source_file": pdf_path.name,
        "account_id": account_id, "account_last4": account_number[-4:],
        "statement_type": "account", "balance_check": "reconciled",
        "period_start": period_start, "period_end": period_end,
        "opening_balance": str(opening), "closing_balance": str(closing),
        "bank_income": str(bank_income), "bank_expense": str(bank_expense),
        "operations": operations,
    }


def _parse_card(pdf, pdf_path: Path, first: str, period_start: str, period_end: str, source_id: str) -> dict:
    card = CARD.search(first)
    if not card:
        raise StatementError("В выписке по карте не найдены последние цифры карты")
    opening = _header_amount(first, "Баланс на начало периода")
    closing = _header_amount(first, "Баланс на конец периода")
    bank_income = _header_amount(first, "Поступления")
    bank_expense = _header_amount(first, "Расходные операции")
    bank_commission = _header_amount(first, "Комиссия банка")
    owner_name = first.split("Номер карты", 1)[0].strip().splitlines()[-1].strip()
    account_id = sha256(f"card:{owner_name}:{card.group(1)}".encode()).hexdigest()[:16]
    operations: list[dict] = []
    commission_total = Decimal(0)
    for page_number, page in enumerate(pdf.pages, 1):
        edges = _boundaries(page, first_column_right=70)
        for row_number, (top, bottom) in enumerate(zip(edges, edges[1:]), 1):
            date_and_time = _cell(page, 20, 70, top, bottom).split()
            if not date_and_time or not DATE.fullmatch(date_and_time[0]):
                continue
            if len(date_and_time) != 2 or not TIME.fullmatch(date_and_time[1]):
                raise StatementError(f"Страница {page_number}: нет времени операции по карте")
            processed = _cell(page, 70, 130, top, bottom)
            if not DATE.fullmatch(processed):
                raise StatementError(f"Страница {page_number}: нет даты обработки у операции")
            processing_date = _date(processed)
            if not period_start <= processing_date <= period_end:
                raise StatementError(f"Страница {page_number}: дата обработки вне периода выписки")
            amount = _card_money(_cell(page, 200, 270, top, bottom))
            commission_total += _money(_cell(page, 270, 320, top, bottom))
            description = _cell(page, 320, 574, top, bottom)
            if not description:
                raise StatementError(f"Страница {page_number}: пустое описание операции")
            operations.append({
                "id": f"{source_id[:12]}-{page_number}-{row_number}",
                "source_id": source_id, "source_file": pdf_path.name,
                "page": page_number, "row": row_number, "account_id": account_id,
                "operation_date": _date(date_and_time[0]), "operation_time": date_and_time[1],
                "processing_date": processing_date,
                "amount": str(amount), "credit": str(max(amount, Decimal(0))),
                "debit": str(min(amount, Decimal(0))),
                "description": description, "recipient": "", "is_self_recipient": False,
            })
    if commission_total != bank_commission:
        raise StatementError(f"Комиссии по строкам не совпадают с итогом банка: {commission_total}/{bank_commission}")
    return {
        "source_id": source_id, "source_file": pdf_path.name,
        "account_id": account_id, "account_last4": card.group(1),
        "statement_type": "card", "balance_check": "not_applicable_pending_card_transactions",
        "period_start": period_start, "period_end": period_end,
        "opening_balance": str(opening), "closing_balance": str(closing),
        "bank_income": str(bank_income), "bank_expense": str(bank_expense),
        "bank_commission": str(bank_commission),
        "pending_amount": str(_header_amount(first, "В обработке")),
        "operations": operations,
    }


def parse_statement(path: str) -> dict:
    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.is_file():
        raise StatementError(f"Файл не найден: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise StatementError("Ожидается PDF-файл")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                raise StatementError("PDF не содержит страниц")
            first = pdf.pages[0].extract_text() or ""
            period = PERIOD.search(first)
            if not period:
                raise StatementError("Формат выписки пока не поддерживается: не найден период выписки")
            period_start, period_end = map(_date, period.groups())
            if period_start > period_end:
                raise StatementError("Начало периода позже окончания")
            source_id = sha256(pdf_path.read_bytes()).hexdigest()
            if ACCOUNT.search(first) and "Операции по сч" in first:
                result = _parse_account(pdf, pdf_path, first, period_start, period_end, source_id)
            elif CARD.search(first) and "Операции по карте" in first:
                result = _parse_card(pdf, pdf_path, first, period_start, period_end, source_id)
            else:
                raise StatementError("Формат выписки пока не поддерживается: ожидается текстовая выписка по счёту или карте")
    except StatementError:
        raise
    except Exception as exc:
        raise StatementError(f"Не удалось прочитать PDF: {pdf_path.name}") from exc
    operations = result["operations"]
    if not operations:
        raise StatementError("В выписке не найдены операции")
    actual_income = sum((Decimal(o["credit"]) for o in operations), Decimal(0))
    actual_expense = -sum((Decimal(o["debit"]) for o in operations), Decimal(0))
    if (actual_income, actual_expense) != (Decimal(result["bank_income"]), Decimal(result["bank_expense"])):
        raise StatementError(
            "Суммы строк не совпадают с итогами банка: "
            f"приход {actual_income}/{result['bank_income']}, расход {actual_expense}/{result['bank_expense']}"
        )
    return result


def merge_statements(statements: list[dict]) -> list[dict]:
    """Keep the largest occurrence count of each transaction per account."""
    by_source: dict[str, dict] = {s["source_id"]: s for s in statements}
    retained: dict[tuple, list[dict]] = {}
    for statement in by_source.values():
        occurrence: Counter[tuple] = Counter()
        for operation in statement["operations"]:
            key = (
                operation["account_id"], operation["operation_date"],
                operation["processing_date"], operation.get("operation_time", ""), operation["amount"],
                operation["description"].casefold(), operation["recipient"].casefold(),
            )
            occurrence[key] += 1
            retained.setdefault(key, [])
            if len(retained[key]) < occurrence[key]:
                retained[key].append(operation)
    return sorted(
        (item for group in retained.values() for item in group),
        key=lambda o: (o["processing_date"], o["operation_date"], o["source_id"], o["page"], o["row"]),
    )
