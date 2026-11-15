from datetime import datetime
import pytest

from app.image_processing.metadata import normalize_exif_text, parse_exif_datetime


@pytest.mark.parametrize(
    "value,expected",
    [
        ("samsung\x00\x00", "samsung"),
        (123456, None),
        ("    ", None)
    ]
)
def test_normalize_exif_text(value: object, expected: str | None) -> None:
    assert normalize_exif_text(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026:09:06 13:24:57", datetime(2026, 9, 6, 13, 24, 57)),
        ("2026:09:06 13:24:57\x00\x00", datetime(2026, 9, 6, 13, 24, 57)),
        ("2026:16:06", None),
        ("2026:16:06 13Í:24:57", None),
        ("2026:09:06", None),
        ("datum", None),
        (None, None),
        (123456, None)
    ]
)
def test_parse_exif_datetime(value: str, expected: datetime | None   ) -> None:
    assert parse_exif_datetime(value) == expected

