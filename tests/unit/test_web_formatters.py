from datetime import datetime, timezone

from src.presentation.web.formatters import datetime_lima, display_field


def test_dates_show_lima_day_and_requested_format():
    instant = datetime(2026, 9, 24, 5, 6, 7, tzinfo=timezone.utc)
    assert datetime_lima(instant) == "24/09/2026 00:06:07"
    assert display_field("2026-09-22T16:56:16+00:00", "ts") == "22/09/2026 11:56:16"
    assert display_field("OK", "status") == "OK"
