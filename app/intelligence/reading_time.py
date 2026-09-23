from __future__ import annotations

import math
import re

KOREAN_CHARACTER = re.compile(r"[\uac00-\ud7a3]")
LATIN_WORD = re.compile(r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b")


class ReadingTimeEstimator:
    version = "reading-time-v1"
    korean_characters_per_minute = 500
    latin_words_per_minute = 200

    def estimate_seconds(self, content: str) -> int:
        korean_count = len(KOREAN_CHARACTER.findall(content))
        latin_count = len(LATIN_WORD.findall(content))
        seconds = (
            korean_count / self.korean_characters_per_minute * 60
            + latin_count / self.latin_words_per_minute * 60
        )
        return math.ceil(seconds)

    def count_units(self, content: str) -> int:
        return len(KOREAN_CHARACTER.findall(content)) + len(LATIN_WORD.findall(content))
