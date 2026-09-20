import pytest

from app.pipeline.normalization import normalize_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  이현중  농구 ", "이현중 농구"),
        ("ＡＩ・Tech", "ai tech"),
        ("Lee   Hyunjung", "lee hyunjung"),
        ("Café—AI", "café ai"),
        ("C / C++ / C#", "c c++ c#"),
    ],
)
def test_normalize_text_is_deterministic_without_transliteration(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_programming_language_symbols_do_not_collapse_to_same_name() -> None:
    assert len({normalize_text("C"), normalize_text("C++"), normalize_text("C#")}) == 3


@pytest.mark.parametrize("raw", ["❤️", "✈️", "☕️", "👩‍💻"])
def test_symbol_only_graphemes_do_not_leave_invisible_keys(raw: str) -> None:
    assert normalize_text(raw) == ""
