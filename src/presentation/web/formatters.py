from datetime import datetime, timezone
import json
from zoneinfo import ZoneInfo

from src.infrastructure.settings import get_settings


def json_pretty(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def datetime_lima(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    else:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo(get_settings().timezone)).strftime("%d/%m/%Y %H:%M:%S")


def display_field(value, field_name: str) -> str:
    key = field_name.lower()
    if key in {"ts", "run_ts", "fechahora"} or key.endswith(("_at", "_ts", "_date")) or "fecha" in key:
        return datetime_lima(value)
    return "—" if value is None else str(value)
