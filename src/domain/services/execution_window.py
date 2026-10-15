from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def expected_activity_period(window: dict, now: datetime):
    """Return the due lookback interval in UTC, or None outside an expected window."""
    local = now.astimezone(ZoneInfo(window.get("timezone") or "America/Lima"))
    days = window.get("weekdays") or []
    start = time.fromisoformat(window["start_time"])
    end = time.fromisoformat(window["end_time"])
    active = None
    for day in (local.date(), local.date() - timedelta(days=1)):
        if day.weekday() not in days or day.isoformat() in (window.get("exceptions") or []):
            continue
        start_dt = datetime.combine(day, start, local.tzinfo)
        end_dt = datetime.combine(day, end, local.tzinfo)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        if start_dt <= local <= end_dt:
            active = start_dt
            break
    if active is None:
        return None
    minutes = int(window["expected_frequency_minutes"]) + int(window.get("tolerance_minutes") or 0)
    if minutes < 1 or local - active < timedelta(minutes=minutes):
        return None
    return max(active, local - timedelta(minutes=minutes)).astimezone(timezone.utc), now.astimezone(timezone.utc)
