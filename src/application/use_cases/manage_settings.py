from sqlalchemy import select

from src.infrastructure.database.models.monitor import (
    ErrorCatalog, ExecutionWindow, MonitorAudit, MonitoringThreshold, NotificationChannel,
)

MODELS = {
    "thresholds": MonitoringThreshold,
    "windows": ExecutionWindow,
    "catalog": ErrorCatalog,
    "channels": NotificationChannel,
}

FIELDS = {
    "thresholds": {"pi_id", "duration_seconds", "started_minutes", "no_activity_minutes", "min_success_rate", "max_errors", "max_dq_percent", "max_retries", "max_duplicates"},
    "windows": {"pi_id", "weekdays", "start_time", "end_time", "expected_frequency_minutes", "tolerance_minutes", "timezone", "exceptions"},
    "catalog": {"code", "origin", "category", "severity", "description", "recommendation", "owner", "active"},
    "channels": {"name", "type", "recipients", "min_severity", "schedule", "templates", "active", "secret_reference"},
}


def as_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def list_settings(session, section: str):
    model = MODELS[section]
    return [as_dict(obj) for obj in session.scalars(select(model).order_by(model.id.desc()).limit(200))]


def save_setting(session, section: str, data: dict, actor: str, item_id: int | None = None):
    if set(data) - FIELDS[section]:
        raise ValueError("Campo no permitido")
    if section == "channels" and any(key in data for key in ("password", "token", "secret", "webhook_url")):
        raise ValueError("Las credenciales deben guardarse fuera de la base")
    model = MODELS[section]
    obj = session.get(model, item_id) if item_id else model()
    if obj is None:
        return None
    before = as_dict(obj) if item_id else None
    for key, value in data.items():
        setattr(obj, key, value)
    session.add(obj)
    session.flush()
    session.add(MonitorAudit(actor=actor, action="update" if item_id else "create", entity=model.__tablename__, entity_id=str(obj.id), before_json=before, after_json=as_dict(obj)))
    session.commit()
    return as_dict(obj)
