from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import asyncio
import json

import pytest
from openai import OpenAIError

from finance_tracker.ai import ClassificationBatch, ClassifiedItem, agent_search, classify_batch, offline_classify
from finance_tracker import mcp_server
from finance_tracker import pipeline
from finance_tracker import cli
from finance_tracker import merchant_rules
from finance_tracker.parser import StatementError, merge_statements, parse_statement
from finance_tracker.privacy import HIDDEN_PURPOSE, redact


FAKE_ACCOUNT = "0" * 20
FAKE_TRANSFER_ACCOUNT = "1" * 20


def test_overlap_merging_keeps_legitimate_repeated_rows():
    base = {
        "account_id": "account-a", "operation_date": "2026-01-02", "processing_date": "2026-01-03",
        "amount": "-100.00", "description": "Одинаковая покупка", "recipient": "Магазин",
    }
    original = [{**base, "id": f"first-{i}", "source_id": "first", "page": 1, "row": i} for i in (1, 2)]
    overlap = [{**base, "id": f"second-{i}", "source_id": "second", "page": 1, "row": i} for i in (1, 2)]
    overlap += [{**base, "id": "second-3", "source_id": "second", "page": 1, "row": 3, "amount": "-50.00"}]
    merged = merge_statements([{"source_id": "first", "operations": original}, {"source_id": "second", "operations": overlap}])
    assert len(merged) == 3
    assert sum(op["amount"] == "-100.00" for op in merged) == 2


def test_corrupt_and_unsupported_pdfs_are_explained(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a PDF")
    with pytest.raises(StatementError, match="Не удалось прочитать PDF"):
        parse_statement(str(bad))


def test_synthetic_account_pdf_is_parsed_by_column_boundaries(tmp_path):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    fonts = [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    font = next((candidate for candidate in fonts if candidate.exists()), None)
    if font is None:
        pytest.skip("Не найден Unicode-шрифт для синтетического PDF")
    pdfmetrics.registerFont(TTFont("SyntheticUnicode", str(font)))
    path = tmp_path / "synthetic.pdf"
    page = canvas.Canvas(str(path), pagesize=(595, 842))
    page.setFont("SyntheticUnicode", 8)
    page.drawString(20, 760, "TEST_OWNER")
    page.drawString(20, 740, f"Номер счёта {FAKE_ACCOUNT} (RUB)")
    page.drawString(20, 720, "Период выписки 01.01.2024 - 31.01.2024")
    page.drawString(20, 690, "Баланс на начало периода 100.00 RUB")
    page.drawString(300, 690, "Поступления 0.00 RUB")
    page.drawString(20, 670, "Баланс на конец периода 50.00 RUB")
    page.drawString(300, 670, "Расходные операции 50.00 RUB")
    page.drawString(20, 620, "Операции по счёту")
    for top in (300, 340):
        page.line(20, 842 - top, 80, 842 - top)
    for x, text in ((25, "05.01.2024"), (85, "06.01.2024"), (155, "-50.00 RUB"),
                    (235, "0.00 RUB"), (315, "-50.00 RUB"), (395, "Оплата товаров и услуг")):
        page.drawString(x, 842 - 323, text)
    page.save()
    statement = parse_statement(str(path))
    assert len(statement["operations"]) == 1
    assert statement["operations"][0]["description"] == "Оплата товаров и услуг"
    assert statement["bank_expense"] == "50.00"


def test_synthetic_card_pdf_uses_card_currency_and_keeps_purchase_times(tmp_path):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    fonts = [Path("/System/Library/Fonts/Supplemental/Arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    font = next((candidate for candidate in fonts if candidate.exists()), None)
    if font is None:
        pytest.skip("Не найден Unicode-шрифт для синтетического PDF")
    pdfmetrics.registerFont(TTFont("SyntheticCardUnicode", str(font)))
    path = tmp_path / "card.pdf"
    page = canvas.Canvas(str(path), pagesize=(595, 842))
    page.setFont("SyntheticCardUnicode", 8)
    headers = [
        (20, 760, "TEST_OWNER"), (20, 740, "Номер карты 0000"),
        (20, 720, "Период выписки 12.01.2024 - 18.01.2024"),
        (20, 690, "Баланс на начало периода 100.00 RUB"),
        (300, 690, "В обработке 900.00 RUB"),
        (20, 670, "Баланс на конец периода 700.00 RUB"),
        (300, 670, "Расходные операции 200.00 RUB"),
        (20, 650, "Поступления 0.0 RUB"), (300, 650, "Комиссия банка 0.0 RUB"),
        (20, 620, "Операции по карте"),
    ]
    for x, y, value in headers:
        page.drawString(x, y, value)
    for row, operation_time in enumerate(("13:06:20", "13:09:41")):
        top = 300 + 30 * row
        page.line(20, 842 - top, 70, 842 - top)
        for x, value in ((22, "11.01.2024"), (72, "13.01.2024"), (132, "0.0 RUB"),
                         (202, "-100.0"), (272, "0.0 RUB"), (322, "Оплата товаров и услуг. TEST_SHOP.")):
            page.drawString(x, 842 - (top + 10), value)
        page.drawString(22, 842 - (top + 22), operation_time)
    page.line(20, 842 - 360, 70, 842 - 360)
    page.save()
    statement = parse_statement(str(path))
    assert statement["statement_type"] == "card"
    assert statement["balance_check"] == "not_applicable_pending_card_transactions"
    assert statement["bank_expense"] == "200.00"
    assert [op["operation_time"] for op in statement["operations"]] == ["13:06:20", "13:09:41"]
    assert len(merge_statements([statement, statement])) == 2


def test_rag_rule_can_explain_cash_withdrawal(tmp_path, monkeypatch):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "goals.md").write_text("Снятие наличных в банкомате — оплата аренды квартиры.\n", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "KNOWLEDGE", knowledge)
    monkeypatch.setattr(mcp_server, "INDEX", tmp_path / "index.sqlite3")
    assert mcp_server.index_knowledge(mode="offline")["chunks"] == 1
    notes = mcp_server.search_knowledge("снятие наличных аренда", 3, mode="offline")
    operation = {"id": "cash", "amount": "-37000.00", "description": "Снятие наличных в банкомате", "recipient": ""}
    item = offline_classify(operation, notes)
    assert (item.flow, item.category, item.uncertain) == ("expense", "Жильё", False)


def test_semantic_index_finds_paraphrase_and_reuses_vectors(tmp_path, monkeypatch):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "housing.md").write_text("Сумма из банкомата покрывает ежемесячную аренду квартиры.", encoding="utf-8")
    (knowledge / "food.md").write_text("Продукты покупаются в супермаркете.", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "KNOWLEDGE", knowledge)
    monkeypatch.setattr(mcp_server, "INDEX", tmp_path / "index.sqlite3")
    mcp_server._QUERY_VECTORS.clear()
    calls = []

    def fake_embedding(texts, model):
        calls.append((tuple(texts), model))
        return [[1.0, 0.0] if "аренду" in text or "жилья" in text else [0.0, 1.0] for text in texts]

    monkeypatch.setattr(mcp_server, "_embed_texts", fake_embedding)
    first = mcp_server.index_knowledge(mode="semantic", embedding_model="fake-a")
    assert first["chunks"] == 2 and first["cached_vectors"] == 0
    assert mcp_server.index_knowledge(mode="semantic", embedding_model="fake-a")["cached_vectors"] == 2
    assert len(calls) == 1
    hits = mcp_server.search_knowledge("Получение бумажных денег для жилья", mode="semantic", embedding_model="fake-a")
    assert hits[0]["path"] == "housing.md"
    assert hits[0]["score"] > hits[1]["score"]
    assert mcp_server.index_knowledge(mode="semantic", embedding_model="fake-b")["cached_vectors"] == 0
    assert len(calls) == 3  # Initial index, query, and new-model index.


def test_empty_semantic_index_uses_no_api(tmp_path, monkeypatch):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    monkeypatch.setattr(mcp_server, "KNOWLEDGE", knowledge)
    monkeypatch.setattr(mcp_server, "INDEX", tmp_path / "index.sqlite3")
    monkeypatch.setattr(mcp_server, "_embed_texts", lambda *_: pytest.fail("API called for empty knowledge base"))
    assert mcp_server.index_knowledge(mode="semantic")["chunks"] == 0
    assert mcp_server.search_knowledge("аренда", mode="semantic") == []


def test_embedding_api_failure_is_explained(tmp_path, monkeypatch):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "goals.md").write_text("Финансовая цель: жильё.", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "KNOWLEDGE", knowledge)
    monkeypatch.setattr(mcp_server, "INDEX", tmp_path / "index.sqlite3")

    def unavailable(*args):
        raise OpenAIError("No connection")

    monkeypatch.setattr(mcp_server, "_embed_texts", unavailable)
    result = mcp_server.index_knowledge(mode="semantic")
    assert "Не удалось получить эмбеддинги OpenAI" in result["error"]


def test_model_creates_query_during_analysis_and_tool_calls_are_bounded():
    class FakeItem:
        type = "function_call"
        name = "search_knowledge"
        call_id = "call-1"
        arguments = json.dumps({"query": "Как отнести снятие для жилья?", "limit": 3})

        def model_dump(self, **kwargs):
            return {"type": self.type, "name": self.name, "call_id": self.call_id, "arguments": self.arguments}

    class FakeResponses:
        def __init__(self):
            self.count = 0

        def create(self, **kwargs):
            self.count += 1
            assert not queries if self.count == 1 else True
            assert kwargs["tools"][0]["name"] == "search_knowledge"
            assert kwargs["tool_choice"] == ("required" if self.count == 1 else "auto")
            return SimpleNamespace(output=[FakeItem()])

    queries = []

    async def search(query, limit):
        queries.append((query, limit))
        return [{"path": "housing.md", "text": "Аренда жилья", "score": 0.91}]

    client = SimpleNamespace(responses=FakeResponses())
    history, trace = asyncio.run(agent_search(client, "gpt-4.1", stage="classification", payload=[{"id": "cash"}], search=search, max_calls=2, require_search=True))
    assert queries == [("Как отнести снятие для жилья?", 3)] * 2
    assert len(trace) == 2
    assert any(item.get("type") == "function_call_output" and "housing.md" in item["output"] for item in history)


def test_reporting_agent_can_search_after_receiving_metrics():
    class ToolCall:
        type = "function_call"
        name = "search_knowledge"
        call_id = "report-search"
        arguments = json.dumps({"query": "Какие цели связаны с расходами на жильё?", "limit": 2})

        def model_dump(self, **kwargs):
            return {"type": self.type, "name": self.name, "call_id": self.call_id, "arguments": self.arguments}

    class Responses:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            assert "metrics" in kwargs["input"][0]["content"]
            return SimpleNamespace(output=[ToolCall()] if self.calls == 1 else [])

    queries = []

    async def search(query, limit):
        queries.append(query)
        return [{"path": "goals.md", "text": "Цель — резерв на жильё.", "score": 0.87}]

    client = SimpleNamespace(responses=Responses())
    _, trace = asyncio.run(agent_search(client, "gpt-4.1", stage="reporting", payload={"metrics": {"expense": "100.00"}}, search=search, max_calls=3))
    assert queries == ["Какие цели связаны с расходами на жильё?"]
    assert trace[0]["hits"][0]["path"] == "goals.md"


def test_year_long_period_is_counted_across_all_days():
    operations = [{
        "id": "one", "amount": "-366.00", "flow": "expense", "category": "Продукты",
        "operation_date": "2024-06-15", "processing_date": "2024-06-15", "description": "Покупка", "uncertain": False,
    }]
    statements = [{
        "source_file": "synthetic.pdf", "period_start": "2024-01-01", "period_end": "2024-12-31",
        "bank_income": "0.00", "bank_expense": "366.00", "opening_balance": "366.00", "closing_balance": "0.00",
    }]
    metrics = mcp_server.calculate_metrics(operations, statements)
    assert metrics["statement_period"]["covered_days"] == 366
    assert metrics["average_expense_day"] == "1.00"


def test_openai_classification_uses_structured_output_and_rejects_missing_rows():
    class FakeResponses:
        def __init__(self, items):
            self.items = items
            self.kwargs = None

        def parse(self, **kwargs):
            self.kwargs = kwargs
            return type("Response", (), {"output_parsed": ClassificationBatch(items=self.items)})()

    operation = {"id": "purchase", "amount": "-100.00", "description": "Магазин", "recipient": ""}
    responses = FakeResponses([ClassifiedItem(id="purchase", flow="expense", category="Продукты", uncertain=False, reason="Магазин")])
    client = type("Client", (), {"responses": responses})()
    assert classify_batch(client, "gpt-4.1", [operation], {})[0].category == "Продукты"
    assert responses.kwargs["text_format"] is ClassificationBatch
    operation["description_hidden"] = True
    masked = classify_batch(client, "gpt-4.1", [operation], {})[0]
    assert masked.category == "Не определено" and masked.uncertain is True
    responses.items = []
    with pytest.raises(RuntimeError, match="пропустил"):
        classify_batch(client, "gpt-4.1", [operation], {})


def _private_input():
    statement = {
        "source_id": "raw-source-hash", "source_file": f"PERSON_NAME_account_{FAKE_ACCOUNT}.pdf",
        "account_id": "raw-account-hash", "account_last4": "0000", "statement_type": "account",
        "balance_check": "reconciled", "period_start": "2024-01-12", "period_end": "2024-01-18",
        "opening_balance": "150.00", "closing_balance": "0.00", "bank_income": "0.00", "bank_expense": "150.00",
    }
    base = {
        "source_id": statement["source_id"], "source_file": statement["source_file"],
        "account_id": statement["account_id"], "page": 1,
        "operation_date": "2024-01-17", "processing_date": "2024-01-18",
        "credit": "0.00", "recipient": "PERSON_NAME", "is_self_recipient": True,
    }
    operations = [
        {**base, "id": "raw-id-1", "row": 1, "amount": "-50.00", "debit": "-50.00",
         "description": f"Перевод между своими счетами. Перечисление средств на счет N {FAKE_TRANSFER_ACCOUNT} от 17.01.2024 PERSON_NAME"},
        {**base, "id": "raw-id-2", "row": 2, "amount": "-100.00", "debit": "-100.00",
         "is_self_recipient": False, "description": "Оплата PERSON_NAME на телефон PHONE_NUMBER"},
    ]
    return statement, operations


def test_redaction_is_allowlisted_and_keeps_accounting_facts():
    statement, operations = _private_input()
    preview = redact([statement], operations)
    serialized = json.dumps(preview, ensure_ascii=False)
    for private in ("PERSON_NAME", FAKE_TRANSFER_ACCOUNT, FAKE_ACCOUNT, "PHONE_NUMBER", "raw-source-hash", "raw-account-hash"):
        assert private not in serialized
    assert preview["operations"][0]["description"] == "Перевод между своими счетами"
    assert preview["operations"][0]["is_self_recipient"] is True
    assert preview["operations"][1]["description"] == HIDDEN_PURPOSE
    assert preview["operations"][1]["recipient"] == ""
    assert [op["amount"] for op in preview["operations"]] == ["-50.00", "-100.00"]
    assert [op["processing_date"] for op in preview["operations"]] == ["2024-01-18"] * 2
    assert preview["review"]["generic_description_count"] == 1


@pytest.mark.parametrize(("raw", "expected"), [
    (f"Заработная плата от PERSON_NAME, счёт {FAKE_ACCOUNT}", "Заработная плата"),
    ("Кешбэк от банка, отправитель PERSON_NAME", "Кешбэк"),
    (f"Снятие наличных, банкомат {FAKE_ACCOUNT}", "Снятие наличных"),
    ("Оплата товаров и услуг. TEST_SHOP. PERSON_NAME", HIDDEN_PURPOSE),
])
def test_redaction_uses_fixed_safe_descriptions(raw, expected):
    statement, operations = _private_input()
    operations = [{**operations[1], "description": raw}]
    clean = redact([statement], operations)["operations"][0]
    assert clean["description"] == expected
    assert clean["recipient"] == ""


def test_local_merchant_rules_are_loaded_from_ignored_data_file(tmp_path, monkeypatch):
    path = tmp_path / "merchant_rules.json"
    path.write_text(json.dumps([{
        "marker": "TEST_SHOP", "label": "Покупка в тестовом магазине", "category": "Тестовая категория",
    }], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(merchant_rules, "RULES_PATH", path)
    merchant_rules.rules.cache_clear()
    try:
        statement, operations = _private_input()
        operation = {**operations[1], "description": "Оплата товаров и услуг. TEST_SHOP. PERSON_NAME"}
        clean = redact([statement], [operation])["operations"][0]
        assert clean["description"] == "Покупка в тестовом магазине"
        assert clean["recipient"] == ""
        classified = offline_classify(clean, [])
        assert (classified.category, classified.uncertain) == ("Тестовая категория", False)
    finally:
        merchant_rules.rules.cache_clear()


def test_preview_rejects_changes_after_save(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "OUTPUT", tmp_path)
    statement, operations = _private_input()
    saved = mcp_server.write_redaction_preview("check", redact([statement], operations))
    path = Path(saved["path"])
    assert path.stat().st_mode & 0o777 == 0o600
    assert mcp_server.read_redaction_preview("check", saved["sha256"])["operations"][0]["amount"] == "-50.00"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert "изменён" in mcp_server.read_redaction_preview("check", saved["sha256"])["error"]


def test_cli_treats_wrapped_confirmation_refusal_as_clean_stop(monkeypatch, capsys):
    async def declined(*_args, **_kwargs):
        raise ExceptionGroup("MCP session", [pipeline.ConfirmationDeclined("Анализ остановлен")])

    monkeypatch.setattr(cli, "run", declined)
    assert cli.main(["unused.pdf", "--offline"]) == 2
    assert "Анализ остановлен" in capsys.readouterr().out


def test_pipeline_does_not_call_openai_before_approval_and_uses_preview_afterward(tmp_path, monkeypatch):
    statement, operations = _private_input()
    monkeypatch.setattr(mcp_server, "OUTPUT", tmp_path)
    calls = []
    model_payloads = []

    class Context:
        def __init__(self, value):
            self.value = value

        async def __aenter__(self):
            return self.value

        async def __aexit__(self, *_):
            return False

    class Session:
        async def initialize(self):
            return None

    monkeypatch.setattr(pipeline, "stdio_client", lambda *_: Context((None, None)))
    monkeypatch.setattr(pipeline, "ClientSession", lambda *_: Context(Session()))

    async def fake_tool(_session, name, arguments):
        calls.append(name)
        if name == "parse_pdf":
            return {**statement, "operations": operations}
        if name == "merge_operations":
            return operations
        if name == "write_redaction_preview":
            return mcp_server.write_redaction_preview(**arguments)
        if name == "read_redaction_preview":
            result = mcp_server.read_redaction_preview(**arguments)
            if "error" in result:
                raise RuntimeError(result["error"])
            return result
        if name == "index_knowledge":
            return {"chunks": 0}
        if name == "calculate_metrics":
            return mcp_server.calculate_metrics(**arguments)
        if name == "write_report":
            return {"json": "saved.json", "markdown": "saved.md"}
        raise AssertionError(name)

    monkeypatch.setattr(pipeline, "_tool", fake_tool)
    monkeypatch.setattr(pipeline, "OpenAI", lambda **_: calls.append("OpenAI") or SimpleNamespace())

    async def fake_search(_client, _model, *, stage, payload, **_):
        model_payloads.append((stage, payload))
        return [], []

    def fake_classify(_client, _model, batch, *_args, **_kwargs):
        model_payloads.append(("structured_classification", batch))
        return [ClassifiedItem(id=op["id"], flow="expense", category="Не определено", uncertain=True, reason="Скрыто") for op in batch]

    def fake_narrative(_client, _model, metrics, *_args, **_kwargs):
        model_payloads.append(("structured_report", metrics))
        return pipeline.Narrative(observations=[], recommendations=[])

    monkeypatch.setattr(pipeline, "agent_search", fake_search)
    monkeypatch.setattr(pipeline, "classify_batch", fake_classify)
    monkeypatch.setattr(pipeline, "generate_narrative", fake_narrative)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(pipeline.ConfirmationDeclined):
        asyncio.run(pipeline.run(["private.pdf"], output_name="declined", confirm=lambda *_: False))
    assert "index_knowledge" not in calls and "OpenAI" not in calls and not model_payloads

    calls.clear()
    def tamper(path, *_):
        Path(path).write_text(Path(path).read_text(encoding="utf-8") + " ", encoding="utf-8")
        return True

    with pytest.raises(RuntimeError, match="изменён"):
        asyncio.run(pipeline.run(["private.pdf"], output_name="changed", confirm=tamper))
    assert "index_knowledge" not in calls and "OpenAI" not in calls

    calls.clear()
    result = asyncio.run(pipeline.run(["private.pdf"], output_name="approved", confirm=lambda *_: True))
    assert result["json"] == "saved.json"
    assert calls.index("read_redaction_preview") < calls.index("OpenAI") < calls.index("index_knowledge")
    transmitted = json.dumps(model_payloads, ensure_ascii=False)
    assert "PERSON_NAME" not in transmitted and FAKE_TRANSFER_ACCOUNT not in transmitted
    assert "raw-source-hash" not in transmitted and "raw-account-hash" not in transmitted
    assert HIDDEN_PURPOSE in transmitted
