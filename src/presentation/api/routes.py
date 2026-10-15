from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.application.use_cases.acknowledge_incident import change_status
from src.application.use_cases.analyze_payload import analyze_payload
from src.application.use_cases.detect_failures import scan
from src.application.use_cases.failure_categories import summarize_categories
from src.application.use_cases.get_dashboard_summary import get_dashboard_summary
from src.application.use_cases.get_run_trace import get_run_trace
from src.application.use_cases.manage_rules import list_rules, save_rule
from src.application.use_cases.manage_settings import FIELDS, list_settings, save_setting
from src.application.use_cases.search_runs import search_runs
from src.domain.enums.failure_category import FailureCategory
from src.domain.services.payload_diff import compare_json
from src.infrastructure.database.models.monitor import DetectedIncident
from src.infrastructure.database.repositories.source import SourceRepository, dq_issues, events, runs
from src.infrastructure.database.repositories.source import sanitize
from src.infrastructure.database.queries.sap_inconsistencies import search as search_sap_inconsistencies
from src.presentation.dependencies import current_user, monitor_session, period, require_role

router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])


class RuleInput(BaseModel):
    code: str
    name: str
    category: str
    evaluator: str
    pi_id: str | None = None
    parameters: dict = Field(default_factory=dict)
    severity: str = "alta"
    active: bool = True


class PayloadRuleInput(BaseModel):
    pi_id: str
    name: str
    json_path: str
    validation_type: str
    parameters: dict = Field(default_factory=dict)
    message: str
    severity: str = "alta"
    stage: str = "input"
    active: bool = True


class AnalyzeInput(BaseModel):
    pi_id: str
    payload: dict | list


class CompareInput(BaseModel):
    before: dict | list
    after: dict | list


def result(items, total, available=True):
    return {"source_available": available, "items": items, "total": total}


@router.get("/dashboard/summary")
def dashboard_summary(hours: int = 168, pi_id: str | None = None, status: str | None = None):
    start, end = period(hours)
    return get_dashboard_summary(start, end, {"pi_id": pi_id, "status": status})


@router.get("/dashboard/failure-categories")
def failure_categories(hours: int = 168, db: Session = Depends(monitor_session)):
    start, end = period(hours)
    return summarize_categories(db, runs.source_available, start, end)


@router.get("/runs")
def list_runs(hours: int = 168, pi_id: str | None = None, status: str | None = None, run_id: str | None = None, queue_name: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    start, end = period(hours)
    items, total = search_runs(start, end, {"pi_id": pi_id, "status": status, "run_id": run_id, "queue_name": queue_name}, limit, offset)
    return result(items, total, runs.source_available)


@router.get("/runs/{run_ts}/{run_id}")
def run_detail(run_ts: datetime, run_id: str):
    row = runs.get_run(run_ts, run_id)
    if row is None:
        raise HTTPException(404, "Ejecución no encontrada")
    return row


@router.get("/runs/{run_ts}/{run_id}/trace")
def run_trace(run_ts: datetime, run_id: str):
    trace = get_run_trace(run_ts, run_id)
    if trace is None:
        raise HTTPException(404, "Ejecución no encontrada")
    return trace


@router.get("/events")
def list_events(hours: int = 168, run_id: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    rows, total = events.search(*period(hours), {"run_id": run_id}, limit, offset)
    return result(rows, total, events.source_available)


@router.get("/dq-issues")
def list_dq(hours: int = 168, run_id: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    rows, total = dq_issues.search(*period(hours), {"run_id": run_id}, limit, offset)
    return result(rows, total, dq_issues.source_available)


@router.get("/incidents")
def incidents(status: str | None = None, category: str | None = None, db: Session = Depends(monitor_session)):
    stmt = select(DetectedIncident).order_by(DetectedIncident.last_seen_at.desc()).limit(200)
    if status:
        stmt = stmt.where(DetectedIncident.status == status)
    if category:
        stmt = stmt.where(DetectedIncident.category == category)
    return [{c.name: getattr(row, c.name) for c in DetectedIncident.__table__.columns} for row in db.scalars(stmt)]


@router.post("/incidents/scan")
def scan_incidents(hours: int = 24, db: Session = Depends(monitor_session), user=Depends(require_role("administrador"))):
    return {"created": scan(*period(hours), db)}


@router.post("/incidents/{incident_id}/acknowledge")
def acknowledge(incident_id: int, db: Session = Depends(monitor_session), user=Depends(require_role("operador"))):
    item = change_status(db, incident_id, "reconocido", user["name"])
    if item is None:
        raise HTTPException(404)
    return {"id": item.id, "status": item.status}


@router.post("/incidents/{incident_id}/resolve")
def resolve(incident_id: int, db: Session = Depends(monitor_session), user=Depends(require_role("operador"))):
    item = change_status(db, incident_id, "resuelto", user["name"])
    if item is None:
        raise HTTPException(404)
    return {"id": item.id, "status": item.status}


@router.get("/payload-inconsistencies")
def inconsistencies(hours: int = 168, pi_id: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    try:
        return search_sap_inconsistencies(*period(hours), pi_id or None, limit, offset)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/payloads/analyze")
def analyze(body: AnalyzeInput, db: Session = Depends(monitor_session), user=Depends(require_role("analista"))):
    if len(str(body.payload)) > 262144:
        raise HTTPException(413, "Payload demasiado grande")
    return {"items": sanitize(analyze_payload(body.pi_id, body.payload, list_rules(db, "payload")))}


@router.post("/payloads/compare")
def compare_payloads(body: CompareInput):
    if len(str(body.before)) + len(str(body.after)) > 524288:
        raise HTTPException(413, "Payload demasiado grande")
    return {"items": sanitize(compare_json(body.before, body.after))}


@router.get("/config/integration-templates")
def templates():
    return result(SourceRepository("iisupao", "plantilla_integracion").templates(), 0, runs.source_available)


@router.get("/config/rules")
def rules(db: Session = Depends(monitor_session)):
    return list_rules(db, "monitoring")


@router.post("/config/rules")
def create_rule(body: RuleInput, db: Session = Depends(monitor_session), user=Depends(require_role("analista"))):
    try:
        return {"id": save_rule(db, "monitoring", body.model_dump(), user["name"]).id}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/config/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleInput, db: Session = Depends(monitor_session), user=Depends(require_role("analista"))):
    try:
        row = save_rule(db, "monitoring", body.model_dump(), user["name"], rule_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if row is None:
        raise HTTPException(404)
    return {"id": row.id}


@router.get("/config/payload-rules")
def payload_rules(db: Session = Depends(monitor_session)):
    return list_rules(db, "payload")


@router.post("/config/payload-rules")
def create_payload_rule(body: PayloadRuleInput, db: Session = Depends(monitor_session), user=Depends(require_role("analista"))):
    try:
        return {"id": save_rule(db, "payload", body.model_dump(), user["name"]).id}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/config/payload-rules/{rule_id}")
def update_payload_rule(rule_id: int, body: PayloadRuleInput, db: Session = Depends(monitor_session), user=Depends(require_role("analista"))):
    try:
        row = save_rule(db, "payload", body.model_dump(), user["name"], rule_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if row is None:
        raise HTTPException(404)
    return {"id": row.id}


@router.get("/config/{section}")
def get_settings_section(section: str, db: Session = Depends(monitor_session)):
    if section not in FIELDS:
        raise HTTPException(404)
    return list_settings(db, section)


@router.post("/config/{section}")
def create_settings_section(section: str, data: dict, db: Session = Depends(monitor_session), user=Depends(require_role("analista"))):
    if section not in FIELDS:
        raise HTTPException(404)
    if section == "channels" and user["role"] != "administrador":
        raise HTTPException(403)
    try:
        return save_setting(db, section, data, user["name"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/config/{section}/{item_id}")
def update_settings_section(section: str, item_id: int, data: dict, db: Session = Depends(monitor_session), user=Depends(require_role("analista"))):
    if section not in FIELDS:
        raise HTTPException(404)
    if section == "channels" and user["role"] != "administrador":
        raise HTTPException(403)
    try:
        result = save_setting(db, section, data, user["name"], item_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if result is None:
        raise HTTPException(404)
    return result
