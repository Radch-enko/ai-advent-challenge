from copia.api.service import _valid_task_report


def test_task_report_requires_answer_focused_template() -> None:
    report = (
        "## Итоговый ответ\n\nDone\n\n### Детали\n\nThe result is ready.\n\n### Ограничения\n\nНет"
    )

    assert _valid_task_report(report) is True


def test_task_report_rejects_workflow_focused_template() -> None:
    report = (
        "## Отчёт о выполнении\n\n### Задача\nTest\n\n### План\n\n"
        "1. First — Выполнено\n\n### Итог\nDone\n\n"
        "### Проверка\n- passed\n\n### Ограничения\n- Нет\n\n### Статус\nГотово"
    )

    assert _valid_task_report(report) is False


def test_task_report_rejects_extra_headings() -> None:
    report = (
        "## Итоговый ответ\n\nDone\n\n### Детали\n\nThe result is ready.\n\n"
        "### Дополнительный статус\n\nГотово\n\n### Ограничения\n\nНет"
    )

    assert _valid_task_report(report) is False
