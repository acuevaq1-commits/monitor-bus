from datetime import datetime, timedelta, timezone
from collections.abc import Mapping

from src.domain.entities.detected_incident import DetectedIncident
from src.domain.enums.failure_category import FailureCategory as C


def evaluate_run(run: dict, now: datetime, started_limit_minutes: int = 30, duration_limit_seconds: int = 600) -> list[DetectedIncident]:
    """Pure initial evaluators; each finding includes the composite source key."""
    ts = run.get("ts")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if not isinstance(ts, datetime):
        return []
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    base = dict(detected_at=now, pi_id=run.get("pi_id"), run_id=str(run.get("run_id", "")), run_ts=ts, corr_id=run.get("corr_id"))
    out = []

    def add(category: C, title: str, severity: str = "alta", evidence: dict | None = None):
        out.append(DetectedIncident(category.value, severity, title, evidence=evidence or {}, **base))

    status = str(run.get("status") or "").upper()
    if status in {"FAILED", "ERROR"}:
        add(C.FAILED_RUN, "Ejecución fallida", "critica", {"status": status})
    if status == "STARTED" and now - ts > timedelta(minutes=started_limit_minutes):
        add(C.STUCK_RUN, "Ejecución bloqueada", "critica", {"minutes": started_limit_minutes})
    error = run.get("error_count")
    if isinstance(error, int) and error > 0:
        add(C.FAILED_RUN, "Registros con error", "alta", {"error_count": error})
    executed, ok, total = (run.get(k) for k in ("executed", "ok_count", "total"))
    if all(isinstance(x, int) for x in (executed, ok, error)) and ok + error != executed:
        add(C.COUNTERS, "Contadores inconsistentes", evidence={"executed": executed, "ok_count": ok, "error_count": error})
    if isinstance(executed, int) and isinstance(total, int) and (executed > total or (status in {"SUCCESS", "COMPLETED", "FINISHED"} and executed < total)):
        add(C.COUNTERS, "Total de registros inconsistente", evidence={"executed": executed, "total": total})
    if not str(run.get("corr_id") or "").strip() or str(run.get("corr_id")).lower() == "no-corr-id":
        add(C.TRACE, "Correlación ausente", "media")
    finished = run.get("finished_at")
    if isinstance(finished, str):
        finished = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    if isinstance(finished, datetime):
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        if finished < ts:
            add(C.TIME, "Fin anterior al inicio", "alta")
        elif (finished - ts).total_seconds() > duration_limit_seconds:
            add(C.PERFORMANCE, "Duración superior al umbral", "media", {"seconds": int((finished - ts).total_seconds())})
    message = " ".join(str(run.get(key) or "") for key in ("error_message", "message", "error", "response_text"))[:4096].lower()
    if any(token in message for token in ("timeout", "connection refused", "dns", "tls", "connection reset")):
        add(C.NETWORK, "Falla de conectividad", "alta")
    http_status = run.get("http_status") or run.get("status_code")
    try:
        http_number = int(http_status)
    except (TypeError, ValueError):
        http_number = None
    if http_number and http_number >= 500:
        add(C.HTTP, "Respuesta HTTP del servidor", "alta", {"http_status": http_number})
    response = run.get("response_json") or run.get("response")
    if isinstance(response, Mapping):
        messages = response.get("messages") or response.get("return") or []
        if isinstance(messages, Mapping):
            messages = [messages]
        if any(isinstance(item, Mapping) and str(item.get("type") or item.get("TYPE") or "").upper() in {"E", "A"} for item in messages):
            add(C.SAP, "Respuesta funcional SAP con error", "critica")
        expected = {"00021": ("BusinessPartner",), "00022": ("SalesOrder",), "00023": ("AccountingDocument",)}.get(str(run.get("pi_id")))
        if expected and http_number and 200 <= http_number < 300 and not any(response.get(key) for key in expected):
            add(C.SAP, "Respuesta SAP sin identificador esperado", "alta")
    return out


def evaluate_related(run: dict, events: list[dict], dq_issues: list[dict], now: datetime) -> list[DetectedIncident]:
    ts = run.get("ts")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if not isinstance(ts, datetime):
        return []
    base = dict(detected_at=now, pi_id=run.get("pi_id"), run_id=str(run.get("run_id", "")), run_ts=ts, corr_id=run.get("corr_id"))
    out = []
    errors = [event for event in events if str(event.get("level") or event.get("severity") or "").upper() == "ERROR"]
    if errors and str(run.get("status") or "").upper() not in {"FAILED", "ERROR"}:
        out.append(DetectedIncident(C.TRACE.value, "alta", "Evento ERROR en ejecución no fallida", evidence={"count": len(errors)}, **base))
    if str(run.get("status") or "").upper() in {"FAILED", "ERROR"} and not errors and not any(run.get(key) for key in ("error_message", "message", "error")):
        out.append(DetectedIncident(C.TRACE.value, "media", "Ejecución fallida sin detalle de error", **base))
    critical_dq = [issue for issue in dq_issues if str(issue.get("severity") or issue.get("level") or "").lower() in {"critical", "critica", "crítica"}]
    if critical_dq:
        out.append(DetectedIncident(C.DATA_QUALITY.value, "critica", "Problemas críticos de calidad de datos", evidence={"count": len(critical_dq)}, **base))
    return out
