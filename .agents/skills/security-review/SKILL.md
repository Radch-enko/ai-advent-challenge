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
