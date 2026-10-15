from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from src.domain.services.rule_evaluator import evaluate_run, evaluate_related
from src.domain.services.execution_window import expected_activity_period
from src.domain.enums.failure_category import FailureCategory
from src.infrastructure.database.models.monitor import DetectedIncident, IncidentOccurrence, MonitoringThreshold, ExecutionWindow
from src.infrastructure.database.repositories.source import runs, events, dq_issues


def scan(start: datetime, end: datetime, session, limit: int = 200):
    if not runs.source_available:
        return 0
    rows, _ = runs.search(start, end, {}, limit, 0)
    created = 0
    thresholds = {row.pi_id: row for row in session.scalars(select(MonitoringThreshold))}
    for run in rows:
        ts = datetime.fromisoformat(str(run["ts"]).replace("Z", "+00:00"))
        detailed = runs.get_run(ts, str(run["run_id"])) or run
        related_events, _ = events.search(ts - timedelta(days=1), ts + timedelta(days=1), {"run_id": run["run_id"]}, 100, 0)
        related_dq, _ = dq_issues.search(ts - timedelta(days=1), ts + timedelta(days=1), {"run_id": run["run_id"]}, 100, 0)
        threshold = thresholds.get(str(run.get("pi_id")))
        findings = evaluate_run(detailed, datetime.now(timezone.utc), threshold.started_minutes if threshold else 30, threshold.duration_seconds if threshold else 600) + evaluate_related(detailed, related_events, related_dq, datetime.now(timezone.utc))
        for finding in findings:
            existing = session.scalar(select(DetectedIncident).where(DetectedIncident.category == finding.category, DetectedIncident.run_ts == finding.run_ts, DetectedIncident.run_id == finding.run_id, DetectedIncident.title == finding.title))
            if existing:
                existing.last_seen_at = finding.detected_at
                continue
            incident = DetectedIncident(category=finding.category, severity=finding.severity, title=finding.title, detected_at=finding.detected_at, last_seen_at=finding.detected_at, pi_id=finding.pi_id, run_id=finding.run_id, run_ts=finding.run_ts, corr_id=finding.corr_id, business_key=finding.business_key, evidence_json=finding.evidence)
            session.add(incident)
            session.flush()
            session.add(IncidentOccurrence(incident_id=incident.id, run_ts=finding.run_ts, run_id=finding.run_id))
            created += 1
    for window in session.scalars(select(ExecutionWindow)):
        period = expected_activity_period({c.name: getattr(window, c.name) for c in ExecutionWindow.__table__.columns}, end)
        if period is None:
            continue
        _, total = runs.search(period[0], period[1], {"pi_id": window.pi_id}, 1, 0)
        if total:
            continue
        existing = session.scalar(select(DetectedIncident).where(DetectedIncident.category == FailureCategory.MISSING_RUN.value, DetectedIncident.pi_id == window.pi_id, DetectedIncident.status != "resuelto", DetectedIncident.run_id.is_(None)))
        if existing:
            existing.last_seen_at = end
            existing.occurrence_count += 1
        else:
            session.add(DetectedIncident(category=FailureCategory.MISSING_RUN.value, severity="alta", title="Integración sin actividad esperada", detected_at=end, last_seen_at=end, pi_id=window.pi_id, evidence_json={"window_id": window.id, "from": period[0].isoformat(), "to": period[1].isoformat()}))
            created += 1
    session.commit()
    return created
