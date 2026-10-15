from sqlalchemy import select
from src.domain.services.payload_validator import SUPPORTED
from src.infrastructure.database.models.monitor import MonitoringRule, PayloadRule, MonitorAudit

EVALUATORS = {"failed_run", "stuck_run", "missing_run", "error_count", "counter_mismatch", "total_mismatch", "error_event", "missing_error_detail", "missing_corr_id", "duplicate_business_key", "network_http", "sap_functional", "missing_sap_id", "critical_dq", "payload_rule", "orphan_record", "negative_duration", "slow_run"}


def save_rule(session, kind: str, data: dict, actor: str, rule_id: int | None = None):
    model = PayloadRule if kind == "payload" else MonitoringRule
    if kind == "payload" and data.get("validation_type") not in SUPPORTED:
        raise ValueError("Tipo de validación no admitido")
    if kind != "payload" and data.get("evaluator") not in EVALUATORS:
        raise ValueError("Evaluador no admitido")
    obj = session.get(model, rule_id) if rule_id else model()
    if rule_id and obj is None:
        return None
    before = {c.name: getattr(obj, c.name) for c in model.__table__.columns} if rule_id else None
    for key, value in data.items():
        if key in model.__table__.columns and key != "id":
            setattr(obj, key, value)
    session.add(obj)
    session.flush()
    after = {c.name: getattr(obj, c.name) for c in model.__table__.columns}
    session.add(MonitorAudit(actor=actor, action="update" if rule_id else "create", entity=model.__tablename__, entity_id=str(obj.id), before_json=before, after_json=after))
    session.commit()
    return obj


def list_rules(session, kind: str):
    model = PayloadRule if kind == "payload" else MonitoringRule
    return [{c.name: getattr(obj, c.name) for c in model.__table__.columns} for obj in session.scalars(select(model).order_by(model.id.desc()).limit(200))]
