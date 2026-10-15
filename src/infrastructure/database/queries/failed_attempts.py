"""Failed attempts grouped by Lima day, Banner ID, and readable error."""
from datetime import datetime
import json

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from src.infrastructure.database.repositories.source import sanitize, source_engine, table
from src.infrastructure.database.queries.sap_inconsistencies import RESULT_QUEUE


SUPPORTED_PI = {"00021": "Nuevos BP fallidos", "00022": "Cargos", "00023": "Pagos"}
IDENTIFIER_LABELS = {pi_id: "ID BANNER" for pi_id in SUPPORTED_PI}
PAGE_SIZE = 50


def _fields(source):
    summary = source.c.summary_json
    pi_id = source.c.pi_id
    result_item = summary["json_exec"]["payload"]["data"][0]
    banner_id = func.nullif(func.btrim(case(
        (pi_id == "00021", result_item["BPEXT"].astext),
        (pi_id == "00022", result_item["KUNNR"].astext),
        else_=result_item["PARTNER"].astext,
    )), "")
    error_body = summary["failed_items"][0]["body"].astext
    failed_count = case(
        (func.jsonb_typeof(summary["failed_items"]) == "array",
         func.jsonb_array_length(summary["failed_items"])), else_=0)
    http_status = summary["json_exec"]["http_status"].astext
    failed_http_status = summary["failed_items"][0]["status_code"].astext
    failed = or_(
        func.upper(source.c.status).in_(("ERROR", "FAILED")),
        failed_count > 0,
        http_status.like("4%"), http_status.like("5%"),
        failed_http_status.like("4%"), failed_http_status.like("5%"),
    )
    return pi_id, banner_id, error_body, failed


def summary(start: datetime | None = None, end: datetime | None = None):
    source = table("iislog", "iis_run")
    cards = {pi_id: {"pi_id": pi_id, "name": name, "attempts": 0, "identifiers": 0,
                     "identifier_label": IDENTIFIER_LABELS[pi_id]}
             for pi_id, name in SUPPORTED_PI.items()}
    if source is None:
        for card in cards.values():
            card["attempts"] = card["identifiers"] = None
        return cards
    pi_id, identifier, _, failed = _fields(source)
    date_clauses = [source.c.ts >= start] if start is not None else []
    if end is not None:
        date_clauses.append(source.c.ts < end)
    statement = (select(pi_id.label("pi_id"), func.count().label("attempts"),
                        func.count(func.distinct(identifier)).label("identifiers"))
                 .where(source.c.queue_name == RESULT_QUEUE, pi_id.in_(SUPPORTED_PI), failed, identifier.is_not(None), *date_clauses)
                 .group_by(pi_id))
    with source_engine().connect() as connection:
        for row in connection.execute(statement).mappings():
            cards[row["pi_id"]]["attempts"] = row["attempts"]
            cards[row["pi_id"]]["identifiers"] = row["identifiers"]
    return cards


def _detail_statement(pi_id: str, min_attempts: int, start: datetime | None, end: datetime | None):
    if pi_id not in SUPPORTED_PI:
        raise ValueError("Integración no admitida")
    if min_attempts < 1:
        raise ValueError("El mínimo de intentos debe ser mayor o igual a 1")
    source = table("iislog", "iis_run")
    if source is None:
        return None
    json_pi_id, identifier, error_body, failed = _fields(source)
    mpl = table("iislog", "iis_mpl_id")
    readable_error = func.coalesce(func.nullif(func.btrim(mpl.c.texto_legible), ""), error_body) if mpl is not None else error_body
    error_day = func.date(func.timezone("America/Lima", source.c.ts))
    source_rows = source.outerjoin(mpl, and_(source.c.ts == mpl.c.ts, source.c.run_id == mpl.c.run_id)) if mpl is not None else source
    date_clauses = [source.c.ts >= start] if start is not None else []
    if end is not None:
        date_clauses.append(source.c.ts < end)
    grouped = (select(error_day.label("fecha_error"), identifier.label("identifier"), readable_error.label("error_body"),
                      func.count().label("total_intentos_fallidos"), func.max(source.c.ts).label("run_ts"),
                      func.array_agg(aggregate_order_by(source.c.run_id, source.c.ts.desc()))[1].label("run_id"))
               .select_from(source_rows)
               .where(source.c.queue_name == RESULT_QUEUE, json_pi_id == pi_id, failed, identifier.is_not(None), *date_clauses)
               .group_by(error_day, identifier, readable_error).subquery())
    totals = (select(grouped, func.sum(grouped.c.total_intentos_fallidos)
                     .over(partition_by=(grouped.c.fecha_error, grouped.c.identifier)).label("total_por_identificador"))
              .subquery())
    return (select(totals).where(totals.c.total_por_identificador >= min_attempts)
            .order_by(totals.c.fecha_error.desc(), totals.c.identifier, totals.c.total_intentos_fallidos.desc()))


def _format_row(row):
    safe_body = sanitize(row["error_body"])
    if isinstance(safe_body, (dict, list)):
        safe_body = json.dumps(safe_body, ensure_ascii=False, indent=2)
    return {"identifier": row["identifier"], "fecha_error": row["fecha_error"], "error_body": safe_body,
            "run_ts": row["run_ts"], "run_id": row["run_id"],
            "total_intentos_fallidos": row["total_intentos_fallidos"],
            "total_por_identificador": row["total_por_identificador"]}


def detail(pi_id: str, page: int = 1, min_attempts: int = 1, start: datetime | None = None, end: datetime | None = None):
    statement = _detail_statement(pi_id, min_attempts, start, end)
    if statement is None:
        return {"source_available": False, "items": [], "has_next": False}
    statement = statement.limit(PAGE_SIZE + 1).offset((max(page, 1) - 1) * PAGE_SIZE)
    with source_engine().connect() as connection:
        rows = list(connection.execute(statement).mappings())
    return {"source_available": True, "items": [_format_row(row) for row in rows[:PAGE_SIZE]], "has_next": len(rows) > PAGE_SIZE}


def export_rows(pi_id: str, min_attempts: int = 1, start: datetime | None = None, end: datetime | None = None):
    statement = _detail_statement(pi_id, min_attempts, start, end)
    if statement is None:
        return
    with source_engine().connect() as connection:
        for row in connection.execution_options(stream_results=True).execute(statement).mappings():
            yield _format_row(row)
