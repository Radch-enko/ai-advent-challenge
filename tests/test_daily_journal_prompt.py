from pathlib import Path


def test_daily_journal_prompt_auto_saves_diary_information_without_rag_footer() -> None:
    prompt = Path("src/copia/daily_journal/prompts/daily_journal.md").read_text(
        encoding="utf-8"
    )

    assert "Не жди слов «запиши», «добавь» или «обнови»" in prompt
    assert "сразу подготовь MCP-вызов" in prompt
    assert "Идеи и наблюдения» — впечатления" in prompt
    assert "Не добавляй к подтверждению напоминание о RAG" in prompt
    assert "После успешной записи сообщай, что файл обновлён, и напоминай" not in prompt
