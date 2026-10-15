from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.application.use_cases.get_dashboard_summary import get_dashboard_summary
from src.application.use_cases.failure_categories import summarize_categories
from src.application.use_cases.get_run_trace import get_run_trace
from src.application.use_cases.search_runs import search_runs
from src.domain.enums.failure_category import FailureCategory
from src.infrastructure.database.models.monitor import DetectedIncident
from src.infrastructure.database.repositories.source import dq_issues, events, runs
from src.infrastructure.database.queries.sap_inconsistencies import search as search_sap_inconsistencies
from src.infrastructure.database.queries.failed_attempts import IDENTIFIER_LABELS, SUPPORTED_PI as FAILED_ATTEMPT_PI, detail as failed_attempts_detail, export_rows as export_failed_attempt_rows, summary as failed_attempts_summary
from src.infrastructure.database.queries.common_errors import search as search_common_errors
from src.infrastructure.database.queries.operational_incidents import KINDS as OPERATIONAL_KINDS, SAP_DAYS, STUCK_MINUTES, detail as operational_detail, summary as operational_summary
from src.infrastructure.database.queries.trace_search import FLOWS, search as search_trace, surrogate_history
from src.infrastructure.settings import get_settings
from src.presentation.dependencies import admin_setup_required, check_csrf, current_web_user, monitor_session, new_csrf, period, verify_login
from src.presentation.web.formatters import datetime_lima, display_field, json_pretty
from src.presentation.web.payload_excel import INCIDENT_COLUMNS, workbook

router = APIRouter()
PAYLOAD_PAGE_SIZE = 15
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
templates.env.filters["datetime_lima"] = datetime_lima
templates.env.filters["display_field"] = display_field
templates.env.filters["json_pretty"] = json_pretty


def render(request: Request, template: str, **kwargs):
    current_url = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return templates.TemplateResponse(request, template, {"user": request.session.get("user"), "environment": get_settings().environment, "csrf": request.session.get("csrf"), "current_url": current_url, **kwargs})


def safe_return_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if value.startswith("/") and not value.startswith("//") and not parsed.scheme and not parsed.netloc and parsed.path in {"/payloads", "/trace", "/runs", "/incidents", "/incidents/rules", "/common-errors", *(f"/incidents/{kind}" for kind in OPERATIONAL_KINDS), *(f"/incidents/failed-attempts/{pi_id}" for pi_id in FAILED_ATTEMPT_PI)}:
        return value
    return None


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "login.html", error=None, setup_required=admin_setup_required())


@router.post("/login")
def login(request: Request, username: str = Form(), password: str = Form()):
    if not verify_login(username, password):
        return render(request, "login.html", error="Credenciales inválidas" if not admin_setup_required() else None, setup_required=admin_setup_required())
    request.session["user"] = {"name": username, "role": "administrador"}
    request.session["csrf"] = new_csrf()
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf: str = Form()):
    check_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def calendar_range(date_from: str, date_to: str) -> tuple[date, date, datetime, datetime]:
    today = datetime.now(ZoneInfo(get_settings().timezone)).date()
    if not date_from and not date_to:
        first, last = today - timedelta(days=6), today
    else:
        try:
            first, last = date.fromisoformat(date_from), date.fromisoformat(date_to)
        except ValueError as exc:
            raise HTTPException(422, "Indique ambas fechas válidas en formato AAAA-MM-DD") from exc
        if first > last:
            raise HTTPException(422, "La fecha inicial debe ser anterior o igual a la final")
    local_tz = ZoneInfo(get_settings().timezone)
    start = datetime.combine(first, time.min, local_tz).astimezone(timezone.utc)
    end = (datetime.combine(last, time.min, local_tz) + timedelta(days=1)).astimezone(timezone.utc)
    return first, last, start, end


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, date_from: str = "", date_to: str = "", pi_id: str | None = None, status: str | None = None, user=Depends(current_web_user), db: Session = Depends(monitor_session)):
    first, last, start, end = calendar_range(date_from, date_to)
    summary = get_dashboard_summary(start, end, {"pi_id": pi_id, "status": status})
    categories = summarize_categories(db, runs.source_available, start, end, {"pi_id": pi_id, "status": status})
    run_query = urlencode({"date_from": first.isoformat(), "date_to": last.isoformat(), **({"pi_id": pi_id} if pi_id else {}), **({"status": status} if status else {})})
    payload_query = urlencode({"date_from": first.isoformat(), "date_to": last.isoformat(), **({"pi_id": pi_id} if pi_id else {})})
    return render(request, "dashboard.html", title="Resumen general", summary=summary, categories=categories, date_from=first, date_to=last, pi_id=pi_id or "", status=status or "", run_query=run_query, payload_query=payload_query, updated=datetime.now(ZoneInfo(get_settings().timezone)))


@router.get("/runs", response_class=HTMLResponse)
def run_list(request: Request, hours: int = 168, pi_id: str | None = None, status: str | None = None, queue_name: str | None = None, date_from: str = "", date_to: str = "", page: int = 1, user=Depends(current_web_user)):
    page = max(page, 1)
    start, end = calendar_range(date_from, date_to)[2:] if date_from or date_to else period(hours)
    rows, total = search_runs(start, end, {"pi_id": pi_id, "status": status, "queue_name": queue_name}, 50, (page - 1) * 50)
    filters = {"hours": hours, **({"date_from": date_from, "date_to": date_to} if date_from and date_to else {}), **({"pi_id": pi_id} if pi_id else {}), **({"status": status} if status else {}), **({"queue_name": queue_name} if queue_name else {})}
    return render(request, "list.html", title="Ejecuciones", kind="runs", items=rows, total=total, page=page, hours=hours, pi_id=pi_id or "", status=status or "", queue_name=queue_name or "", date_from=date_from, date_to=date_to, filter_query=urlencode(filters), available=runs.source_available)


@router.get("/events", response_class=HTMLResponse)
def event_list(request: Request, hours: int = 168, page: int = 1, user=Depends(current_web_user)):
    rows, total = events.search(*period(hours), {}, 50, (max(page, 1) - 1) * 50)
    return render(request, "list.html", title="Eventos", kind="events", items=rows, total=total, page=page, hours=hours, available=events.source_available)


@router.get("/dq-issues", response_class=HTMLResponse)
def dq_list(request: Request, hours: int = 168, page: int = 1, user=Depends(current_web_user)):
    rows, total = dq_issues.search(*period(hours), {}, 50, (max(page, 1) - 1) * 50)
    return render(request, "list.html", title="Calidad de datos", kind="dq", items=rows, total=total, page=page, hours=hours, available=dq_issues.source_available)


@router.get("/runs/{run_ts}/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_ts: datetime, run_id: str, return_to: str = "", tab: str = "", user=Depends(current_web_user)):
    trace = get_run_trace(run_ts, run_id, detail=True)
    if trace is None:
        raise HTTPException(404)
    return render(request, "run_detail.html", title=f"Ejecución {run_id} - {datetime_lima(trace['run']['ts'])}", trace=trace, back_url=safe_return_url(return_to) or "/runs", active_tab=7 if tab == "cpi" else 1)


@router.get("/incidents", response_class=HTMLResponse)
def incident_page(request: Request, date_from: str = "", date_to: str = "", user=Depends(current_web_user)):
    first, last, start, end = calendar_range(date_from, date_to)
    inactivity_hours = max(1, get_settings().inactivity_hours)
    return render(request, "incidents.html", title="Intentos fallidos", failed_cards=failed_attempts_summary(start, end), operational_cards=operational_summary(inactivity_hours=inactivity_hours), inactivity_hours=inactivity_hours, sap_days=SAP_DAYS, stuck_minutes=STUCK_MINUTES, date_from=first, date_to=last)


@router.get("/common-errors", response_class=HTMLResponse)
def common_errors_page(request: Request, date_from: str = "", date_to: str = "", page: int = 1, user=Depends(current_web_user)):
    first, last, start, end = calendar_range(date_from, date_to)
    page = max(page, 1)
    findings = search_common_errors(start, end, page)
    return render(request, "common_errors.html", title="Errores comunes", findings=findings,
                  date_from=first, date_to=last, page=page,
                  filter_query=urlencode({"date_from": first.isoformat(), "date_to": last.isoformat()}))


@router.get("/incidents/rules", response_class=HTMLResponse)
def rule_incidents_page(request: Request, category: str | None = None, db: Session = Depends(monitor_session), user=Depends(current_web_user)):
    stmt = select(DetectedIncident).order_by(DetectedIncident.last_seen_at.desc()).limit(200)
    if category:
        stmt = stmt.where(DetectedIncident.category == category)
    rows = list(db.scalars(stmt))
    return render(request, "rule_incidents.html", title="Incidentes de reglas", items=rows, category=category)


@router.get("/incidents/failed-attempts/{pi_id}", response_class=HTMLResponse)
def failed_attempts_page(request: Request, pi_id: str, page: int = 1, min_attempts: int = 1, date_from: str = "", date_to: str = "", user=Depends(current_web_user)):
    if pi_id not in FAILED_ATTEMPT_PI:
        raise HTTPException(404)
    if min_attempts < 1:
        raise HTTPException(422, "La cantidad mínima de intentos debe ser al menos 1")
    first, last, start, end = calendar_range(date_from, date_to)
    page = max(page, 1)
    findings = failed_attempts_detail(pi_id, page, min_attempts, start, end)
    filter_query = urlencode({"date_from": first.isoformat(), "date_to": last.isoformat(), "min_attempts": min_attempts})
    return render(request, "failed_attempts.html", title=f"{FAILED_ATTEMPT_PI[pi_id]} · Intentos fallidos", pi_id=pi_id, flow_name=FAILED_ATTEMPT_PI[pi_id], identifier_label=IDENTIFIER_LABELS[pi_id], page=page, min_attempts=min_attempts, findings=findings, date_from=first, date_to=last, filter_query=filter_query)


@router.get("/incidents/failed-attempts/{pi_id}/export")
def export_failed_attempts(pi_id: str, min_attempts: int = 1, date_from: str = "", date_to: str = "", user=Depends(current_web_user)):
    if pi_id not in FAILED_ATTEMPT_PI:
        raise HTTPException(404)
    if min_attempts < 1:
        raise HTTPException(422, "La cantidad mínima de intentos debe ser al menos 1")
    _, _, start, end = calendar_range(date_from, date_to)
    try:
        file = workbook(None, export_failed_attempt_rows(pi_id, min_attempts, start, end), columns=INCIDENT_COLUMNS)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    def content():
        try:
            while chunk := file.read(65536):
                yield chunk
        finally:
            file.close()

    return StreamingResponse(content(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="intentos_fallidos_{pi_id}.xlsx"'})


@router.get("/incidents/{kind}", response_class=HTMLResponse)
def operational_incident_page(request: Request, kind: str, page: int = 1, user=Depends(current_web_user)):
    if kind not in OPERATIONAL_KINDS:
        raise HTTPException(404)
    page = max(page, 1)
    inactivity_hours = max(1, get_settings().inactivity_hours)
    findings = operational_detail(kind, page, inactivity_hours=inactivity_hours)
    return render(request, "operational_incidents.html", title=OPERATIONAL_KINDS[kind], kind=kind, page=page, findings=findings, inactivity_hours=inactivity_hours, sap_days=SAP_DAYS, stuck_minutes=STUCK_MINUTES)


@router.get("/trace", response_class=HTMLResponse)
def trace_page(request: Request, tab: str = "bp", id_banner: str = "", surrogate: str = "", id_sap: str = "", apellidos: str = "", dni: str = "", status: str = "", date_from: date | None = None, date_to: date | None = None, page: int = 1, submitted: str = "", user=Depends(current_web_user)):
    if tab not in FLOWS:
        raise HTTPException(422, "Pestaña no admitida")
    explicit_dates = date_from is not None or date_to is not None
    if date_from is None and date_to is None:
        date_to = datetime.now(ZoneInfo(get_settings().timezone)).date()
        date_from = date_to - timedelta(days=6)
    if (date_from is None) != (date_to is None):
        raise HTTPException(422, "Indique ambas fechas del rango")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "La fecha inicial debe ser anterior o igual a la final")
    local_tz = ZoneInfo(get_settings().timezone)
    start = datetime.combine(date_from, time.min, local_tz).astimezone(timezone.utc)
    end = (datetime.combine(date_to, time.min, local_tz) + timedelta(days=1)).astimezone(timezone.utc)
    filters = {key: value.strip()[:100] for key, value in {
        "id_banner": id_banner, "id_sap": id_sap if tab != "bp" else "",
        "apellidos": apellidos if tab == "bp" else "",
        "dni": dni if tab == "bp" else "",
        "surrogate": surrogate if tab != "bp" else "",
        "status": status,
    }.items()}
    page = max(page, 1)
    searched = submitted == "1" or any(filters.values()) or explicit_dates
    results = search_trace(tab, filters, page, start, end) if searched else None
    query = {"tab": tab, "submitted": "1", **{key: value for key, value in filters.items() if value}}
    if date_from and date_to:
        query.update(date_from=date_from.isoformat(), date_to=date_to.isoformat())
    return render(request, "trace.html", title="Trazabilidad", tab=tab, filters=filters, date_from=date_from, date_to=date_to, page=page, searched=searched, results=results, filter_query=urlencode(query))


def payload_filters(pi_id, hours, view, q, bp, record_id, surrogate, id_banner, error_http, bldat, date_from, date_to, bp_id="", dni="", mpl_id=""):
    pi_id = pi_id or None
    if pi_id is not None and pi_id not in {"00021", "00022", "00023"}:
        raise HTTPException(422, "pi_id no admitido")
    if view not in {"incidents", "all"}:
        raise HTTPException(422, "vista no admitida")
    q = q.strip()[:100]
    bp, record_id, surrogate, id_banner, error_http, bldat = (value.strip()[:100] for value in (bp, record_id, surrogate, id_banner, error_http, bldat))
    bp_id, dni, mpl_id = (value.strip()[:100] for value in (bp_id, dni, mpl_id))
    if pi_id != "00021":
        bp_id = dni = mpl_id = ""
    if pi_id != "00023":
        id_banner = error_http = bldat = ""
    try:
        date_from = date.fromisoformat(date_from) if date_from.strip() else None
        date_to = date.fromisoformat(date_to) if date_to.strip() else None
    except ValueError as exc:
        raise HTTPException(422, "Indique fechas válidas en formato AAAA-MM-DD") from exc
    if (date_from is None) != (date_to is None):
        raise HTTPException(422, "Indique ambas fechas del rango")
    if date_from and date_to:
        if date_from > date_to:
            raise HTTPException(422, "La fecha inicial debe ser anterior o igual a la final")
        local_tz = ZoneInfo(get_settings().timezone)
        start = datetime.combine(date_from, time.min, local_tz).astimezone(timezone.utc)
        end = (datetime.combine(date_to, time.min, local_tz) + timedelta(days=1)).astimezone(timezone.utc)
    elif q or bp or record_id or surrogate or id_banner or error_http or bldat or bp_id or dni or mpl_id:
        start = end = None
    else:
        start, end = period(hours)
    id_filters = {key: value for key, value in {"bp": bp, "record_id": record_id, "surrogate": surrogate, "id_banner": id_banner, "error_http": error_http, "bldat": bldat, "bp_id": bp_id, "dni": dni, "mpl_id": mpl_id}.items() if value}
    return start, end, date_from, date_to, q, bp, record_id, surrogate, id_banner, error_http, bldat, bp_id, dni, mpl_id, id_filters


@router.get("/payloads/export")
def export_payloads(pi_id: str, hours: int = 168, view: str = "incidents", q: str = "", bp: str = "", record_id: str = "", surrogate: str = "", id_banner: str = "", error_http: str = "", bldat: str = "", date_from: str = "", date_to: str = "", bp_id: str = "", dni: str = "", mpl_id: str = "", export_scope: str = "first500", user=Depends(current_web_user)):
    if pi_id not in {"00021", "00022", "00023"}:
        raise HTTPException(422, "pi_id no admitido")
    if export_scope not in {"first500", "all"}:
        raise HTTPException(422, "opción de descarga no admitida")
    start, end, _, _, q, _, _, _, _, _, _, _, _, _, id_filters = payload_filters(pi_id, hours, view, q, bp, record_id, surrogate, id_banner, error_http, bldat, date_from, date_to, bp_id, dni, mpl_id)

    def rows():
        offset = 0
        while True:
            remaining = 500 - offset if export_scope == "first500" else 200
            if remaining <= 0:
                break
            batch = search_sap_inconsistencies(start, end, pi_id, min(200, remaining), offset, include_all=view == "all", query=q, count_total=False, **id_filters)
            yield from batch["items"]
            if not batch["has_next"] or not batch["items"]:
                break
            offset += len(batch["items"])

    try:
        file = workbook(pi_id, rows())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    def content():
        try:
            while chunk := file.read(65536):
                yield chunk
        finally:
            file.close()

    return StreamingResponse(content(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="payloads_{pi_id}.xlsx"'})


@router.get("/payloads", response_class=HTMLResponse)
def payload_page(request: Request, pi_id: str | None = None, hours: int = 168, page: int = 1, last: bool = False, view: str = "incidents", q: str = "", bp: str = "", record_id: str = "", surrogate: str = "", id_banner: str = "", error_http: str = "", bldat: str = "", date_from: str = "", date_to: str = "", bp_id: str = "", dni: str = "", mpl_id: str = "", user=Depends(current_web_user)):
    start, end, date_from, date_to, q, bp, record_id, surrogate, id_banner, error_http, bldat, bp_id, dni, mpl_id, id_filters = payload_filters(pi_id, hours, view, q, bp, record_id, surrogate, id_banner, error_http, bldat, date_from, date_to, bp_id, dni, mpl_id)
    pi_id = pi_id or None
    page = max(page, 1)
    last_total = None
    if last:
        last_lookup = search_sap_inconsistencies(start, end, pi_id, 1, 0, include_all=view == "all", query=q, force_count=True, **id_filters)
        last_total = last_lookup["total"]
        page = max(1, ((last_total or 0) + PAYLOAD_PAGE_SIZE - 1) // PAYLOAD_PAGE_SIZE)
    findings = search_sap_inconsistencies(start, end, pi_id, PAYLOAD_PAGE_SIZE, (page - 1) * PAYLOAD_PAGE_SIZE, include_all=view == "all", query=q, **id_filters)
    if last_total is not None:
        findings["total"] = last_total
        findings["has_next"] = page * PAYLOAD_PAGE_SIZE < last_total
    if view == "incidents" and not q and not id_filters and page == 1:
        latest_finding = findings["items"][0] if findings["items"] else None
    else:
        first_incident = search_sap_inconsistencies(start, end, pi_id, 1, 0, count_total=False, **id_filters)
        latest_finding = first_incident["items"][0] if first_incident["items"] else None
    latest_result = runs.latest_within(start, end, {"pi_id": pi_id, "queue_name": "que.upao.iisupao.result"})
    total_pages = max(1, ((findings["total"] or 0) + PAYLOAD_PAGE_SIZE - 1) // PAYLOAD_PAGE_SIZE) if findings["total"] is not None else None
    page_numbers = range(max(1, page - 2), min(total_pages, page + 2) + 1) if total_pages is not None else [page]
    filters = {"hours": hours, "view": view}
    if pi_id:
        filters["pi_id"] = pi_id
    if date_from and date_to:
        filters.update(date_from=date_from.isoformat(), date_to=date_to.isoformat())
    if q:
        filters["q"] = q
    filters.update(id_filters)
    filter_query = urlencode(filters)
    view_query = urlencode({**filters, "view": "all" if view == "incidents" else "incidents"})
    clear_query = urlencode({key: value for key, value in filters.items() if key not in {"q", "bp", "record_id", "surrogate", "id_banner", "error_http", "bldat", "bp_id", "dni", "mpl_id"}})
    reset_query = urlencode({key: value for key, value in filters.items() if key not in {"date_from", "date_to"}})
    return render(request, "payloads.html", title="Resultados BP SAP" if view == "all" else "Payloads", pi_id=pi_id, hours=hours, page=page, view=view, q=q, bp=bp, record_id=record_id, surrogate=surrogate, id_banner=id_banner, error_http=error_http, bldat=bldat, bp_id=bp_id, dni=dni, mpl_id=mpl_id, date_from=date_from, date_to=date_to, filter_query=filter_query, view_query=view_query, clear_query=clear_query, reset_query=reset_query, findings=findings, latest_finding=latest_finding, latest_result=latest_result, total_pages=total_pages, page_numbers=page_numbers)


@router.get("/surrogate", response_class=HTMLResponse)
def surrogate_page(request: Request, pi_id: str, surrogate: str, page: int = 1, user=Depends(current_web_user)):
    flow = {"00022": "cargos", "00023": "pagos"}.get(pi_id)
    if flow is None or not surrogate.strip() or len(surrogate) > 100:
        raise HTTPException(422, "SURROGATE o integración no admitidos")
    surrogate = surrogate.strip()
    page = max(page, 1)
    history = surrogate_history(flow, surrogate, page)
    return render(request, "surrogate.html", title="Trazabilidad del SURROGATE", pi_id=pi_id, surrogate=surrogate, page=page, history=history, filter_query=urlencode({"pi_id": pi_id, "surrogate": surrogate}))


@router.get("/config/{section}", response_class=HTMLResponse)
def config_page(request: Request, section: str, user=Depends(current_web_user)):
    allowed = {"rules": "Reglas de monitoreo", "payload-rules": "Reglas de payload", "thresholds": "Umbrales", "windows": "Ventanas de ejecución", "catalog": "Catálogo de errores", "channels": "Canales de alerta", "templates": "Plantillas de integración"}
    if section not in allowed:
        raise HTTPException(404)
    return render(request, "config.html", title=allowed[section], section=section)
