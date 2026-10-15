# Coding policy

- Support Python 3.11 or newer. Put application packages under `src/code_assistance/`.
- Use explicit types, direct control flow, and small modules. Add abstractions only for current boundaries.
- Use Ruff for formatting and linting, and mypy strict mode once the Python package exists.
- Use bounded I/O, timeouts, and clear user-facing errors for provider, Git, MCP, and index failures.
- Keep comments rare and useful; write code comments in Russian.
- Do not edit generated output, caches, virtual environments, or `*.egg-info`.
