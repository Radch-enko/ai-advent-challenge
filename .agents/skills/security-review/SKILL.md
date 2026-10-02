---
name: security-review
description: Используй при ревью работы Copia, затрагивающей secrets, auth/authz, network access, logging, user data, dependencies, CI, deployment, bots или repository security gates.
---

# Security Review

Используй этот skill для focused read-only security review.

Прочитай:

- `AGENTS.md`
- `harness/policies/security.md`
- `harness/policies/testing.md`
- `harness/policies/git.md`
- Current task or review target
- Current `git status --short`, `git diff --stat`, and `git diff`
- Changed files and related security-sensitive code paths

Проверь:

- No secrets, tokens, credentials, signing material или local config не закоммичены.
- Проведи отдельную смысловую проверку на реальные персональные сведения пользователя в review scope: факты из личной базы знаний или профиля, реальные фрагменты и пересказы диалогов, сессионные transcripts/summaries, LLM prompts/results, logs и dumps embeddings, а также содержимое challenge reports, tests, fixtures, evals и examples. Проверяй staged, unstaged и untracked changes; при repository-wide audit проверяй весь доступный repository content. Ищи реальные или узнаваемые факты, даже если имена заменены или текст слегка перефразирован.
- Не считай gitleaks, regex или совпадения по именам файлов достаточной проверкой: оценивай смысл содержимого как LLM reviewer. Если нужные файлы недоступны, исключены из review scope или их нельзя безопасно прочитать, явно укажи это как ограничение, не делая вывод об отсутствии утечки.
- Не читай внешнюю личную базу знаний, реальные `.env`, secrets, keychains, environment values или личную local configuration для сравнения. Если локальный runtime artifact может содержать их, не раскрывай его значения; зафиксируй только путь и причину ограничения.
- При обнаружении вероятной смысловой утечки укажи file и line references, категорию и severity, но не цитируй и не пересказывай само личное сведение. Не переноси такие факты в review report, примеры, tests или другие outputs.
- Secrets не выводятся в logs, command lines, generated artifacts, examples или error paths.
- Auth/authz boundaries соответствуют task и fail closed.
- Network access и dependency additions имеют явное task justification.
- Inputs, deserialization, storage, telemetry и logging не раскрывают sensitive user data.
- CI/deploy scripts не выводят environments, artifacts или tool output, который может содержать secrets.
- `./harness/scripts/security-check.sh` запускался при изменении repository content или указана точная причина его
  отсутствия.

Оставайся read-only. Не просматривай реальные local secrets, keychains, environment values, CI secret values или
untracked secret files.

Сначала сообщай findings, упорядоченные по severity, с concrete file references. Если findings нет, так и укажи и опиши
residual risk.
