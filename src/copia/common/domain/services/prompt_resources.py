import re
from importlib.resources import files


def load_prompt(package: str, filename: str) -> str:
    """Read a prompt Markdown resource packaged alongside its feature."""
    return files(package).joinpath("prompts", filename).read_text(encoding="utf-8").strip()


def render_prompt(package: str, filename: str, **values: str) -> str:
    prompt = load_prompt(package, filename)
    return re.sub(
        r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}",
        lambda match: values[match.group(1)],
        prompt,
    )
