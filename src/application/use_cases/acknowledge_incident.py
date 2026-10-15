from datetime import datetime, timezone
from src.infrastructure.database.models.monitor import DetectedIncident, IncidentAction


def change_status(session, incident_id: int, status: str, actor: str):
    incident = session.get(DetectedIncident, incident_id)
    if incident is None:
        return None
    if status not in {"reconocido", "resuelto", "abierto", "silenciado"}:
        raise ValueError("Estado inválido")
    incident.status = status
    if status == "reconocido":
        incident.acknowledged_at = datetime.now(timezone.utc)
    if status == "resuelto":
        incident.resolved_at = datetime.now(timezone.utc)
    session.add(IncidentAction(incident_id=incident_id, action=status, actor=actor))
    session.commit()
    return incident
