from __future__ import annotations

import re
import unicodedata

WHITESPACE = re.compile(r"\s+")
MEANINGFUL_SYMBOLS = {"+", "#", "&"}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    without_punctuation = "".join(
        _normalize_character(character)
        for character in normalized
    )
    return WHITESPACE.sub(" ", without_punctuation).strip()


def _normalize_character(character: str) -> str:
    codepoint = ord(character)
    if character == "\u200d" or 0xFE00 <= codepoint <= 0xFE0F or 0xE0100 <= codepoint <= 0xE01EF:
        return ""
    if unicodedata.category(character)[0] in {"P", "S"} and character not in MEANINGFUL_SYMBOLS:
        return " "
    return character
