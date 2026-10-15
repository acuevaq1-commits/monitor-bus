from sqlalchemy import select
from src.domain.enums.failure_category import FailureCategory
from src.infrastructure.database.models.monitor import DetectedIncident
from src.infrastructure.database.queries.sap_inconsistencies import count_by_severity
from src.infrastructure.database.repositories.source import runs


MEASURABLE = {FailureCategory.FAILED_RUN, FailureCategory.STUCK_RUN, FailureCategory.SAP}


def summarize_categories(session, source_available: bool, start=None, end=None, filters: dict | None = None):
    results = {category.value: {"category": category.value, "count": 0 if source_available and category in MEASURABLE else None, "critical": 0, "high": 0, "medium": 0, "last_seen": None, "trend": None, "state": "normal" if source_available and category in MEASURABLE else "sin fuente de datos"} for category in FailureCategory}
    for incident in session.scalars(select(DetectedIncident).where(DetectedIncident.status != "resuelto").order_by(DetectedIncident.last_seen_at.desc()).limit(1000)):
        item = results.get(incident.category)
        if item is None:
            continue
        item["count"] = (item["count"] or 0) + 1
        severity_field = {"critica": "critical", "alta": "high", "media": "medium"}.get(incident.severity)
        if severity_field:
            item[severity_field] += 1
        if item["last_seen"] is None:
            item["last_seen"] = incident.last_seen_at
    for item in results.values():
        if item["critical"]:
            item["state"] = "critico"
        elif item["high"] or item["medium"]:
            item["state"] = "advertencia"
    if source_available and start and end:
        run_summary = runs.summary(start, end, filters or {})
        failed_count = sum(run_summary["statuses"].get(status, 0) for status in ("ERROR", "FAILED"))
        failed = results[FailureCategory.FAILED_RUN.value]
        failed["count"] = failed_count
        failed["critical"] = failed_count
        failed["state"] = "critico" if failed_count else "normal"
        stuck_count = run_summary["stuck"] or 0
        stuck = results[FailureCategory.STUCK_RUN.value]
        stuck["count"] = stuck_count
        stuck["critical"] = stuck_count
        stuck["state"] = "critico" if stuck_count else "normal"
        sap = count_by_severity(start, end)
        item = results[FailureCategory.SAP.value]
        item["count"] = sap["total"]
        item["critical"] = sap["critical"]
        item["high"] = sap["high"]
        item["state"] = "critico" if sap["critical"] else "advertencia" if sap["high"] else "normal"
    return sorted(results.values(), key=lambda item: ({"critico": 0, "advertencia": 1, "normal": 2, "sin fuente de datos": 3}[item["state"]], item["category"]))
