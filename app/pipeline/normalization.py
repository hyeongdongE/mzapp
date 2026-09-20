from __future__ import annotations

import re
import unicodedata

WHITESPACE = re.compile(r"\s+")
MEANINGFUL_SYMBOLS = {"+", "#", "&"}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    without_punctuation = "".join(
        " "
        if unicodedata.category(character)[0] in {"P", "S"}
        and character not in MEANINGFUL_SYMBOLS
        else character
        for character in normalized
    )
    return WHITESPACE.sub(" ", without_punctuation).strip()
