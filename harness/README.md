# Harness Copia для AI SDLC

Harness — это локальная для репозитория операционная система Copia для разработки с помощью AI. Она превращает
запросы в задачи с ограниченной областью, направляет реализацию и ревью, а также предоставляет детерминированные
контрольные проверки качества.

## Структура

- `workflows/`: процедуры feature, bugfix, refactoring, planning, review, infrastructure, task authoring и
  test-integrity.
- `policies/`: правила архитектуры, кодирования, тестирования, безопасности и Git.
- `templates/`: артефакты задач, планов, ADR, ревью, завершения и test-integrity.
- `scripts/`: настройка зависимостей, тесты, сборка frontend, lint, проверки безопасности, архитектуры и
  канонические проверки.
- `git-hooks/`: управляемые репозиторием pre-commit и pre-push проверки.
- `evals/`: smoke-сценарии для проверки качества работы агента.

## Жизненный цикл

```text
request -> task context -> plan -> scoped implementation -> focused checks
        -> full check -> diff review -> completion report
```

При реализации через strict feature route используй точную спецификацию задачи, переданную в `/feature`; допустимые
расположения — `docs/tasks/active/` и `docs/tasks/backlog/`. В других workflow используй подходящую active task, если
она существует. Иначе используй явный пользовательский запрос как контекст задачи или сначала создай задачу, если
неоднозначность заставит делать предположения при реализации.

## Команды

```bash
./harness/scripts/check-dependencies.sh
./harness/scripts/test.sh
./harness/scripts/build-check.sh
./harness/scripts/lint.sh
./harness/scripts/security-check.sh
./harness/scripts/architecture-check.sh
./harness/scripts/check.sh
./utils/install-git-hooks.sh
```

`check.sh` — каноническая контрольная проверка. Скрипты неинтерактивны, кроме установки зависимостей, и должны
завершаться с ненулевым кодом, если обязательная проверка не пройдена.
