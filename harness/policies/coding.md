# Coding Policy

- Support Python 3.11 or newer and keep packages under `src/copia`.
- Use Ruff for Python lint and formatting with a 100-column line length.
- Use TypeScript strict checks, ESLint, and Prettier for the React client.
- Prefer typed models, direct control flow, and small public interfaces.
- Keep provider-specific behavior in adapters and browser API calls in `client/src/data`.
- Keep React effects explicit and dependency-safe.
- Add dependencies only for a concrete current requirement and document why.
- Keep comments sparse and useful.
- Do not edit generated output, caches, virtual environments, `node_modules`, `dist`, `.run`, or `*.egg-info`.
