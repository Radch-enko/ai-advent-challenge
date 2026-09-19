---
name: review
description: Используй при ревью task plan, implementation diff или завершённой работы Copia через review workflow.
---

# Review

Используй `harness/workflows/review.md` как нормативный workflow.

Прочитай task, plan при наличии, релевантные architecture docs, changed files, tests и verification claims. Если
изменялись существующие tests, проверь Test Change Report и подготовь Test Integrity verdict. Сначала сообщи findings по
severity с file references, затем open questions и residual risk.

Не редактируй files без явного запроса. Не выполняй commit, push, merge, reset или clean.
