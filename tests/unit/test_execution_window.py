from datetime import datetime, timezone
from src.domain.services.execution_window import expected_activity_period


def test_lima_window_and_exception_day():
    now = datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)  # 11:00 Lima
    window = {"timezone": "America/Lima", "weekdays": [3], "start_time": "08:00", "end_time": "17:00", "expected_frequency_minutes": 60, "tolerance_minutes": 15, "exceptions": []}
    period = expected_activity_period(window, now)
    assert period[0].hour == 14 and period[1] == now
    window["exceptions"] = ["2026-09-24"]
    assert expected_activity_period(window, now) is None
