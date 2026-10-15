# Development harness

This harness provides scoped workflows, policies, templates, and repeatable checks for Code Assistance. It does not implement the CLI itself.

- `workflows/`: feature, bugfix, review, task authoring, and test integrity.
- `policies/`: architecture, coding, testing, security, and Git.
- `templates/`: task, plan, ADR, review, and completion records.
- `scripts/bootstrap-check.sh`: validates this harness before Python package setup.
- `scripts/check.sh`: full gate after `pyproject.toml`, `src/code_assistance/`, `tests/`, and development dependencies exist.

No Git hooks are installed automatically. The source Copia harness included frontend and FastAPI checks; those do not apply to this CLI.
