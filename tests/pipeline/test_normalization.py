import pytest

from app.pipeline.normalization import normalize_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  이현중  농구 ", "이현중 농구"),
        ("ＡＩ・Tech", "ai tech"),
        ("Lee   Hyunjung", "lee hyunjung"),
        ("Café—AI", "café ai"),
    ],
)
def test_normalize_text_is_deterministic_without_transliteration(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected
