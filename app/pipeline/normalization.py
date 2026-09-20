from __future__ import annotations

import re
import unicodedata

WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    without_punctuation = "".join(
        " " if unicodedata.category(character)[0] in {"P", "S"} else character
        for character in normalized
    )
    return WHITESPACE.sub(" ", without_punctuation).strip()
