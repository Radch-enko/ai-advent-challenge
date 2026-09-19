# Infrastructure Workflow

## Назначение

Используй этот workflow для CI/CD, качества validation jobs, repository automation, local hooks, build tooling и
operational scripts.

Этот workflow не предназначен для обычных product features, UI changes, domain logic или server endpoints, если только
task не меняет способ их build, check, release, deploy или automation.

## Критерии входа

Используй этот workflow, если task включает хотя бы одно из следующего:

- CI workflow files, CI runners, job ordering, caching, artifacts, notifications или required checks.
- Harness scripts, evals, Git hooks, validation gates или automation quality.
- Build, packaging, deployment, release или local developer automation.
- Tool configuration, dependency setup или release/deployment automation.
- Изменения secret-handling, environment variables или runtime configuration для infrastructure.

Если task требует только validation results, используй tester workflow. Если task требует только review, используй
`harness/workflows/review.md`.

## Обязательные входные данные

- Task context или explicit user request.
- Затронутая infrastructure surface:
  - CI/CD и jobs.
  - Harness scripts и gates.
  - Git hooks или evals.
  - Deployment или operational automation.
- Ожидаемый quality signal: faster checks, stricter checks, clearer failures, safer automation или documented operational
  behavior.
- Acceptance criteria, сопоставленные с executable commands или explicit manual verification.

## Процедура

1. Прочитай `AGENTS.md` и любые nested `AGENTS.md` в affected directories.
2. Проверь `docs/tasks/active/` и принимай только clearly matching task.
3. Прочитай relevant policies в `harness/policies/`, особенно `security.md`, `testing.md` и `git.md`.
4. До редактирования изучи affected scripts, workflows, configuration и documentation.
5. Определи, затрагивает ли change developer-local checks, CI-only checks, packaging или deployment.
6. Изолируй change от product modules, если только task явно не меняет build validation этих modules.
7. Сохраняй secret safety:
   - Не коммить secrets или local runtime config.
   - Используй placeholders в examples.
   - Не выводи secret values в scripts или logs.
8. Делай scripts non-interactive и возвращай ненулевой код при required failures.
9. Добавляй или обновляй focused tests, eval cases или script validation, когда это практически возможно.
10. Сначала запускай наиболее узкую релевантную command, затем `./harness/scripts/check.sh`, если это возможно.
11. Проверь `git status --short`, `git diff --stat` и `git diff`.
12. Сообщи evidence, assumptions, unresolved risks и checks, которые нельзя было выполнить.

## Рекомендации по verification

Предпочитай deterministic verification в следующем порядке:

- Для harness eval metadata: `./harness/evals/run-evals.sh`.
- Для validation scripts: запусти изменённый script напрямую.
- Для build tooling: запусти наиболее узкую affected Python или frontend command.
- Для repository-wide impact: `./harness/scripts/check.sh`.
- Для CI-only behavior, которое нельзя запустить локально: проверь syntax, где возможно, и сообщи manual или CI-only
  gap.

## Вне области задачи

- Product feature implementation, если infrastructure work не требует минимального supporting change.
- Broad CI/CD redesign без явных acceptance criteria.
- Добавление third-party hosted services или новых dependencies без task justification.
- Создание, чтение или раскрытие secrets.
- Замена существующих gates более слабыми checks.

## Требования к завершению

Completion report должен включать:

- Изменённую infrastructure surface.
- Добавленное или сохранённое quality/automation behavior.
- Выполненные commands и точные results.
- Assumptions по secret-handling.
- CI-only или host-only residual risk.
- Требовался ли `Infrastructurer` по context и почему.
