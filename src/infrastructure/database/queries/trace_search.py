"""Search all run stages for the three Banner–SAP flows."""
from datetime import datetime

from sqlalchemy import Text, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONPATH

from src.infrastructure.database.repositories.source import source_engine, table
from src.infrastructure.database.repositories.source import sanitize


FLOWS = {"bp": "00021", "cargos": "00022", "pagos": "00023"}
PAGE_SIZE = 50


def _exact_json_value(column, value: str):
    # Some identifiers have different names in inline and result payloads.
    # Compare complete JSON scalar values, never fragments of serialized JSON.
    return func.jsonb_path_exists(
        column,
        cast("$.** ? (@ == $needle)", JSONPATH),
        func.jsonb_build_object("needle", cast(value, Text)),
    )


def _exact_json_key(column, key: str, value: str):
    # Keys come from the fixed mapping below, never directly from the request.
    return func.jsonb_path_exists(
        column,
        cast(f"$.**.{key} ? (@ == $needle)", JSONPATH),
        func.jsonb_build_object("needle", cast(value, Text)),
    )


def _contains(value: str):
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(flow: str, filters: dict, page: int = 1, start: datetime | None = None, end: datetime | None = None):
    if flow not in FLOWS:
        raise ValueError("Flujo no admitido")
    engine = source_engine()
    if engine is None:
        return {"source_available": False, "items": [], "has_next": False}
    t = table("iislog", "iis_run")
    clauses = [t.c.pi_id == FLOWS[flow]]
    if start is not None:
        clauses.append(t.c.ts >= start)
    if end is not None:
        clauses.append(t.c.ts < end)
    if flow == "bp":
        if filters.get("id_banner"):
            clauses.append(_exact_json_value(t.c.summary_json, filters["id_banner"]))
        if filters.get("dni"):
            clauses.append(or_(*(_exact_json_key(t.c.summary_json, key, filters["dni"]) for key in ("TAXNUM", "wnrodoc"))))
    elif flow == "cargos":
        cargo_keys = {"id_banner": ("KUNNR",), "surrogate": ("BSTKD",), "id_sap": ("VBELN", "SalesOrder")}
        for key, json_keys in cargo_keys.items():
            if filters.get(key):
                clauses.append(or_(*(_exact_json_key(t.c.summary_json, json_key, filters[key]) for json_key in json_keys)))
    else:
        payment_keys = {"id_banner": ("PARTNER",), "surrogate": ("BSTKD",), "id_sap": ("VBELN", "AccountingDocument")}
        for key, json_keys in payment_keys.items():
            if filters.get(key):
                clauses.append(or_(*(_exact_json_key(t.c.summary_json, json_key, filters[key]) for json_key in json_keys)))
    if filters.get("status"):
        clauses.append(t.c.status == filters["status"].upper())

    result_item = t.c.summary_json["json_exec"]["payload"]["data"][0]
    inline_payload = t.c.summary_json["payload"]
    if filters.get("apellidos"):
        surname = _contains(filters["apellidos"])
        clauses.append(
            result_item["NAME_LAST"].astext.ilike(surname, escape="\\")
            | inline_payload["data"]["person"]["wnameLast"].astext.ilike(surname, escape="\\")
        )

    if flow == "bp":
        banner = func.coalesce(result_item["BPEXT"].astext, inline_payload["data"]["person"]["wbannerId"].astext, inline_payload["data"]["wbannerId"].astext)
        surrogate = literal(None)
        dni = func.coalesce(result_item["TAXNUM"].astext, inline_payload["data"]["person"]["wnrodoc"].astext)
        sap = literal(None)
        reference = func.coalesce(result_item["NAME_LAST"].astext, inline_payload["data"]["person"]["wnameLast"].astext)
    elif flow == "cargos":
        dni = literal(None)
        banner = func.coalesce(result_item["KUNNR"].astext, inline_payload["KUNNR"].astext)
        surrogate = func.coalesce(result_item["BSTKD"].astext, inline_payload["BSTKD"].astext)
        sap = func.coalesce(result_item["VBELN"].astext, inline_payload["VBELN"].astext, result_item["SalesOrder"].astext)
        reference = func.coalesce(result_item["TXT_REFERENCIA"].astext, inline_payload["TXT_REFERENCIA"].astext)
    else:
        dni = literal(None)
        banner = func.coalesce(result_item["PARTNER"].astext, inline_payload["PARTNER"].astext)
        surrogate = func.coalesce(result_item["BSTKD"].astext, inline_payload["BSTKD"].astext)
        sap = func.coalesce(result_item["VBELN"].astext, result_item["AccountingDocument"].astext, inline_payload["VBELN"].astext)
        reference = func.coalesce(result_item["ZVIAPAG"].astext, inline_payload["ZVIAPAG"].astext)

    statement = (
        select(
            t.c.ts, t.c.run_id, t.c.queue_name, t.c.status,
            t.c.error_count,
            banner.label("id_banner"), surrogate.label("surrogate"),
            dni.label("dni"), sap.label("id_sap"), reference.label("reference"),
        )
        .where(*clauses)
        .order_by(t.c.ts.desc(), t.c.run_id.desc())
        .limit(PAGE_SIZE + 1)
        .offset((max(page, 1) - 1) * PAGE_SIZE)
    )
    with engine.connect() as connection:
        rows = [dict(row) for row in connection.execute(statement).mappings()]
    return {"source_available": True, "items": rows[:PAGE_SIZE], "has_next": len(rows) > PAGE_SIZE}


def surrogate_history(flow: str, surrogate: str, page: int = 1):
    if flow not in {"cargos", "pagos"} or not surrogate or len(surrogate) > 100:
        raise ValueError("SURROGATE no admitido")
    engine = source_engine()
    if engine is None:
        return {"source_available": False, "items": [], "total": None, "sent_count": None, "result_count": None, "has_next": False}
    t = table("iislog", "iis_run")
    key = "BSTKD"
    clause = (t.c.pi_id == FLOWS[flow], _exact_json_key(t.c.summary_json, key, surrogate))
    statement = select(t.c.ts, t.c.run_id, t.c.queue_name, t.c.status, t.c.summary_json).where(*clause).order_by(t.c.ts.desc(), t.c.run_id.desc()).limit(PAGE_SIZE + 1).offset((max(page, 1) - 1) * PAGE_SIZE)
    with engine.connect() as connection:
        counts = dict(connection.execute(select(t.c.queue_name, func.count()).where(*clause).group_by(t.c.queue_name)))
        rows = list(connection.execute(statement).mappings())
    items = []
    for row in rows[:PAGE_SIZE]:
        summary = row["summary_json"] if isinstance(row["summary_json"], dict) else {}
        execution = summary.get("json_exec") if isinstance(summary.get("json_exec"), dict) else {}
        failed = summary.get("failed_items") if isinstance(summary.get("failed_items"), list) else []
        first_failure = next((item for item in failed if isinstance(item, dict)), {})
        response = first_failure.get("body") or first_failure.get("error") or execution.get("message") or execution.get("response") or summary.get("message")
        if isinstance(response, (dict, list)):
            response = str(sanitize(response))
        items.append({"ts": row["ts"], "run_id": str(row["run_id"]), "queue_name": row["queue_name"], "status": row["status"], "json_status": execution.get("status"), "http_status": execution.get("http_status"), "response": sanitize(str(response)[:2000]) if response is not None else None})
    return {"source_available": True, "items": items, "total": sum(counts.values()), "sent_count": counts.get("que.upao.iisupao.program.inline", 0), "result_count": counts.get("que.upao.iisupao.result", 0), "has_next": len(rows) > PAGE_SIZE}
