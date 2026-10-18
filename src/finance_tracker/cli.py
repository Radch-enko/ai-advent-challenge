"""Human-friendly command-line interface."""
from __future__ import annotations

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from .pipeline import ConfirmationDeclined, run


ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_EMBEDDING_MODEL"}:
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _setup_logging() -> None:
    directory = ROOT / "logs"
    directory.mkdir(exist_ok=True)
    handler = RotatingFileHandler(directory / "finance.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # HTTP metadata (method, URL, status) is useful; request bodies and keys are never logged.
    logging.getLogger("httpx").setLevel(logging.INFO)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Локальный анализ банковских выписок")
    parser.add_argument("pdf", nargs="+", help="Пути к PDF-выпискам")
    parser.add_argument("--offline", action="store_true", help="Демонстрация без OpenAI API, с простыми правилами")
    parser.add_argument("--name", help="Имя файлов результата без расширения")
    args = parser.parse_args(argv)
    _load_env()
    _setup_logging()
    try:
        saved = asyncio.run(run(args.pdf, offline=args.offline, model=os.getenv("OPENAI_MODEL", "gpt-4.1"), embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"), output_name=args.name))
    except ConfirmationDeclined as exc:
        print(str(exc))
        return 2
    except Exception as exc:
        leaf = exc
        while isinstance(leaf, BaseExceptionGroup) and leaf.exceptions:
            leaf = leaf.exceptions[0]
        if isinstance(leaf, ConfirmationDeclined):
            print(str(leaf))
            return 2
        logging.exception("Pipeline failed")
        message = str(leaf).splitlines()[0]
        if "api" in type(leaf).__name__.lower() or "openai" in type(leaf).__module__.lower():
            message = "Не удалось обратиться к OpenAI API. Проверьте ключ, сеть и доступ к модели."
        elif message.startswith("Error executing tool"):
            message = message.split(":", 1)[-1].strip()
        print(f"Ошибка: {message}. Подробности сохранены в logs/finance.log.", file=sys.stderr)
        return 1
    print(f"Готово. JSON: {saved['json']}")
    print(f"Отчёт: {saved['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
