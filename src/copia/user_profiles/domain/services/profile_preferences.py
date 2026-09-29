from __future__ import annotations

import json
from typing import TYPE_CHECKING

from copia.common.domain.services.prompt_resources import render_prompt

if TYPE_CHECKING:
    from copia.user_profiles.domain.models.user_profile_fields import UserProfileFields


def profile_preferences_json(profile: UserProfileFields) -> str:
    return _profile_preferences_json(profile)


def profile_preferences_block_size(profile: UserProfileFields) -> int:
    escaped = _escape_untrusted_prompt_text(_profile_preferences_json(profile))
    return len(render_prompt("copia.sessions", "user_profile_context.md", preferences=escaped))


def _profile_preferences_json(profile: UserProfileFields) -> str:
    return json.dumps(
        {
            "language": profile.language,
            "tone": profile.tone,
            "verbosity": profile.verbosity,
            "response_format": profile.response_format,
            "constraints": profile.constraints,
        },
        ensure_ascii=False,
        indent=2,
    )


def _escape_untrusted_prompt_text(value: str) -> str:
    return value.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
