from datetime import datetime, timedelta
from src.infrastructure.database.repositories.source import runs


def get_dashboard_summary(start: datetime, end: datetime, filters: dict):
    if not runs.source_available:
        return {"source_available": False, "cards": {}, "statuses": {}, "recent": [], "last_activity": None, "no_activity_24h": None}
    current = runs.summary(start, end, filters)
    previous = runs.summary(start - (end - start), start, filters)
    rows, _ = runs.search(start, end, filters, 10, 0)
    total = current["total"]
    status_counts = current["statuses"]
    finished = sum(count for status, count in status_counts.items() if status not in {"STARTED", "PENDING"})
    success = sum(count for status, count in status_counts.items() if status in {"SUCCESS", "COMPLETED", "FINISHED", "OK"})
    latest = runs.latest_within(end - timedelta(days=30), end, filters)
    last_ts = datetime.fromisoformat(latest["ts"]) if latest else None
    return {"source_available": True, "cards": {"integrations": current["integrations"], "runs": total, "success_rate": round(success * 100 / finished, 1) if finished else None, "errors": sum(status_counts.get(s, 0) for s in ("FAILED", "ERROR")), "stuck": current["stuck"], "mean_seconds": None}, "previous_runs": previous["total"], "statuses": status_counts, "recent": rows, "last_activity": latest, "no_activity_24h": last_ts is None or last_ts < end - timedelta(days=1)}
