# Политика архитектуры

- `src/copia/api` отвечает за FastAPI routes, HTTP models и composition приложения.
- `src/copia/data` отвечает за provider adapters, model metadata, profiles и persistence.
- `src/copia/domain` отвечает за понятия agent, session, routing и context management; domain и data не должны зависеть
  от API package.
- Provider-specific HTTP и обработка credentials должны оставаться в `src/copia/data/providers`.
- `client/src/domain` содержит frontend types, независимые от framework, и не должен зависеть от React, data или UI
  code.
- `client/src/data` может зависеть от frontend domain types, но не должен зависеть от UI components.
- `client/src/ui` может зависеть от domain types; `client/src/App.tsx` — composition layer клиента.
- Public provider-agnostic contracts не должны раскрывать adapter-specific payloads без явного API decision.
- Для каждого production change запускай `./harness/scripts/architecture-check.sh`.
