---
name: feature
description: Используй при реализации новой feature Copia по существующей спецификации задачи через feature workflow.
---

# Feature

Используй `harness/workflows/feature.md` как нормативный workflow.

Загрузи `AGENTS.md`, потребуй ровно один существующий путь к Markdown-спецификации задачи в `docs/tasks/active/` или
`docs/tasks/backlog/` и считай этот явно переданный файл нормативным. Отклоняй отсутствующие или некорректные paths,
вместо того чтобы выводить task context из догадок. Route `/feature` пропускает complexity gate Expert Council и сам
Expert Council. Затем загрузи релевантные architecture docs и policies из `harness/policies/`. Свяжи acceptance
criteria с verification, реализуй минимальное изменение, применяй `harness/workflows/test-integrity-gate.md` при
изменении tests, запускай focused checks и `./harness/scripts/check.sh`, если это возможно, проверь diff и подготовь
отчёт по `harness/templates/completion-report.md`.

Не перестраивай architecture, не скрывай failing checks, не создавай feature-to-feature dependencies и не выполняй
commit/push без явного запроса.
