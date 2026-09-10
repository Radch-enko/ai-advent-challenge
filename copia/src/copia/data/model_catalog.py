from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..domain.models.config import ProviderName


@lru_cache(maxsize=1)
def _context_windows() -> dict[str, dict[str, int]]:
    path = Path(__file__).with_name("model_context_windows.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not load model context windows from {path}") from error

    if not isinstance(data, dict):
        raise RuntimeError("Model context windows catalog must be a JSON object")
    for provider, models in data.items():
        if not isinstance(provider, str) or not isinstance(models, dict):
            raise RuntimeError("Each provider in the model context windows catalog must contain an object")
        if any(not isinstance(model, str) or not isinstance(limit, int) or limit <= 0 for model, limit in models.items()):
            raise RuntimeError("Model context window limits must be positive integers")
    return data


def context_window_for(provider: ProviderName, model: str) -> int | None:
    return _context_windows().get(provider.value, {}).get(model)
