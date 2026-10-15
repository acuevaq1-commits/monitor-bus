"""Live incident cards based on the SAP result runs."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select

from src.domain.services.sap_status_validator import FAILURE, SUCCESS
from src.infrastructure.database.queries.sap_inconsistencies import RESULT_QUEUE
from src.infrastructure.database.repositories.source import sanitize, source_engine, table


FLOW_NAMES = {"00021": "Nuevos BP", "00022": "Cargos", "00023": "Pagos"}
KINDS = {"stuck": "Ejecuciones bloqueadas", "sap": "Errores funcionales SAP", "inactive": "Sin ejecuciones recientes"}
PAGE_SIZE = 50
STUCK_MINUTES = 30
SAP_DAYS = 7


def _sap_failure(source):
    summary = source.c.summary_json
    execution = summary["json_exec"]
    json_status = execution["status"].astext
    http_status = execution["http_status"].astext
    failed_items = summary["failed_items"]
    failed_count = case((func.jsonb_typeof(failed_items) == "array", func.jsonb_array_length(failed_items)), else_=0)
    response_failed = or_(failed_count > 0, func.upper(json_status).in_(FAILURE),
                          json_status.like("4%"), json_status.like("5%"),
                          http_status.like("4%"), http_status.like("5%"))
    return and_(source.c.queue_name == RESULT_QUEUE, source.c.pi_id.in_(FLOW_NAMES),
                func.upper(source.c.status).in_(SUCCESS), response_failed)


def _stuck(source, now):
    return and_(func.upper(source.c.status) == "STARTED", source.c.ts < now - timedelta(minutes=STUCK_MINUTES))


def _latest_per_flow(connection, source):
    rows = connection.execute(select(source.c.pi_id, func.max(source.c.ts).label("last_ts"))
                              .where(source.c.queue_name == RESULT_QUEUE, source.c.pi_id.in_(FLOW_NAMES))
                              .group_by(source.c.pi_id)).mappings()
    return {row["pi_id"]: _as_utc(row["last_ts"]) for row in rows}


def _as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def _inactive_items(latest, now, inactivity_hours):
    cutoff = now - timedelta(hours=inactivity_hours)
    return [{"pi_id": pi_id, "flow_name": name, "last_ts": latest.get(pi_id),
             "hours_without_results": round((now - latest[pi_id]).total_seconds() / 3600, 1) if latest.get(pi_id) else None}
            for pi_id, name in FLOW_NAMES.items() if latest.get(pi_id) is None or latest[pi_id] < cutoff]


def summary(now: datetime | None = None, inactivity_hours: int = 24):
    now = now or datetime.now(timezone.utc)
    source = table("iislog", "iis_run")
    cards = {kind: {"name": name, "count": None} for kind, name in KINDS.items()}
    if source is None:
        return cards
    with source_engine().connect() as connection:
        cards["stuck"]["count"] = connection.scalar(select(func.count()).select_from(source).where(_stuck(source, now))) or 0
        cards["sap"]["count"] = connection.scalar(select(func.count()).select_from(source)
                                                     .where(source.c.ts >= now - timedelta(days=SAP_DAYS), _sap_failure(source))) or 0
        cards["inactive"]["count"] = len(_inactive_items(_latest_per_flow(connection, source), now, inactivity_hours))
    return cards


def detail(kind: str, page: int = 1, now: datetime | None = None, inactivity_hours: int = 24):
    if kind not in KINDS:
        raise ValueError("Tipo de incidente no admitido")
    now = now or datetime.now(timezone.utc)
    source = table("iislog", "iis_run")
    if source is None:
        return {"source_available": False, "items": [], "has_next": False}
    with source_engine().connect() as connection:
        if kind == "inactive":
            items = _inactive_items(_latest_per_flow(connection, source), now, inactivity_hours)
            return {"source_available": True, "items": items, "has_next": False}
        columns = [source.c.ts, source.c.run_id, source.c.pi_id, source.c.status, source.c.queue_name]
        if kind == "stuck":
            statement = select(*columns).where(_stuck(source, now))
        else:
            execution = source.c.summary_json["json_exec"]
            statement = select(*columns, execution["status"].astext.label("json_status"),
                               execution["http_status"].astext.label("http_status"),
                               source.c.summary_json["failed_items"][0]["body"].astext.label("error_body"))
            statement = statement.where(source.c.ts >= now - timedelta(days=SAP_DAYS), _sap_failure(source))
        statement = statement.order_by(source.c.ts.desc(), source.c.run_id.desc()).limit(PAGE_SIZE + 1).offset((max(page, 1) - 1) * PAGE_SIZE)
        rows = list(connection.execute(statement).mappings())
    items = []
    for row in rows[:PAGE_SIZE]:
        item = sanitize(dict(row))
        item["run_id"] = str(item["run_id"])
        item["flow_name"] = FLOW_NAMES.get(item.get("pi_id"), item.get("pi_id") or "—")
        if kind == "stuck":
            item["minutes_elapsed"] = int((now - _as_utc(row["ts"])).total_seconds() // 60)
        items.append(item)
    return {"source_available": True, "items": items, "has_next": len(rows) > PAGE_SIZE}
