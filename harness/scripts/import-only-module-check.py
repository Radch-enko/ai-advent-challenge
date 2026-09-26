#!/usr/bin/env python3
"""Reject Python modules that only re-export imports."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "copia"


def is_reexport_module(statements: list[ast.stmt]) -> bool:
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    if (
        statements
        and isinstance(statements[-1], ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in statements[-1].targets
        )
    ):
        statements = statements[:-1]
    return bool(statements) and all(
        isinstance(statement, (ast.Import, ast.ImportFrom)) for statement in statements
    )


def main() -> int:
    import_only = []
    for path in ROOT.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        statements = ast.parse(path.read_text(encoding="utf-8")).body
        if is_reexport_module(statements):
            import_only.append(path.relative_to(ROOT.parent.parent))

    if not import_only:
        return 0

    for path in sorted(import_only):
        print(f"ERROR: import-only module: {path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
