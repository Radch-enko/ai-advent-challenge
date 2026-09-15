# Architecture Policy

- `src/copia/api` owns FastAPI routes, HTTP models, and application composition.
- `src/copia/data` owns provider adapters, model metadata, profiles, and persistence.
- `src/copia/domain` owns agent, session, routing, and context-management concepts; domain and data must not depend on the API package.
- Provider-specific HTTP and credential handling stays under `src/copia/data/providers`.
- `client/src/domain` contains framework-independent frontend types and must not depend on React, data, or UI code.
- `client/src/data` may depend on frontend domain types but must not depend on UI components.
- `client/src/ui` may depend on domain types; `client/src/App.tsx` is the client composition layer.
- Public provider-agnostic contracts must not expose adapter-specific payloads without an explicit API decision.
- Run `./harness/scripts/architecture-check.sh` for every production change.
