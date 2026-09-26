from typing import Literal

Language = Literal["ru", "en", "auto"]
Tone = Literal["neutral", "friendly", "formal", "direct"]
Verbosity = Literal["concise", "balanced", "detailed"]
ResponseFormat = Literal["plain_text", "markdown", "bullets", "steps", "tables", "code"]
