"""Bounded, read-only JSONB queries for the three SAP integrations."""
from datetime import datetime, timedelta
import json
import re
from sqlalchemy import String, and_, case, cast, func, or_, select

from src.domain.services.sap_status_validator import FAILURE, SUCCESS, classify_status
from src.infrastructure.database.repositories.source import coerce_filter_value, sanitize, sanitize_detail, source_engine, table

RESULT_QUEUE = "que.upao.iisupao.result"
INLINE_QUEUE = "que.upao.iisupao.program.inline"
SUPPORTED_PI = {"00021", "00022", "00023"}
MPL_ID_PATTERN = re.compile(r"\bMPL\s+ID\b[^\r\n:]{0,100}:\s*([A-Za-z0-9_-]{8,128})", re.IGNORECASE)


def _fields(t):
    root = t.c.summary_json
    execution = root["json_exec"]
    json_status = execution["status"].astext
    http_status = execution["http_status"].astext
    failed = root["failed_items"]
    failed_count = case((func.jsonb_typeof(failed) == "array", func.jsonb_array_length(failed)), else_=0)
    status_mismatch = or_(
        and_(func.upper(t.c.status).in_(SUCCESS), or_(func.upper(json_status).in_(FAILURE), json_status.like("4%"), json_status.like("5%"), http_status.like("4%"), http_status.like("5%"))),
        and_(func.upper(t.c.status).in_(FAILURE), or_(func.upper(json_status).in_(SUCCESS), json_status.like("2%"), http_status.like("2%"))),
    )
    mismatch = or_(failed_count > 0, and_(t.c.pi_id != "00021", status_mismatch))
    return json_status, http_status, failed_count, mismatch


def extract_mpl_id(body: str | None) -> str | None:
    match = MPL_ID_PATTERN.search(body or "")
    return match.group(1) if match else None


def bp_mpl_text(mpl_row, error_body: str) -> str | None:
    """Prefer the stored text, then use the MPL ID already present in the run error."""
    return (mpl_row["texto_mpl_id"] if mpl_row else None) or extract_mpl_id(error_body)


def material_numbers(items) -> str | None:
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return None
    values = dict.fromkeys(str(item["MATNR"]) for item in items if isinstance(item, dict) and item.get("MATNR"))
    return ", ".join(values) or None


def payment_messages(failed_items) -> str | None:
    def find(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                return []
        if isinstance(value, dict):
            messages = [str(item) for key, item in value.items() if key.lower() == "mensaje" and item is not None and not isinstance(item, (dict, list))]
            return messages + [message for key, item in value.items() if key.lower() != "mensaje" for message in find(item)]
        if isinstance(value, list):
            return [message for item in value for message in find(item)]
        return []

    messages = dict.fromkeys(message for item in failed_items if isinstance(item, dict) for message in find(item.get("body")) if message.strip())
    return "; ".join(messages)[:2000] or None


def find_cpi_text(run_ts: datetime, run_id: str) -> dict | None:
    mpl_table = table("iislog", "iis_mpl_id")
    if mpl_table is None or "texto_cpi" not in mpl_table.c:
        return None
    statement = (
        select(mpl_table.c.texto_mpl_id, mpl_table.c.texto_legible, mpl_table.c.texto_cpi)
        .where(mpl_table.c.ts == run_ts, mpl_table.c.run_id == coerce_filter_value(mpl_table.c.run_id, run_id))
        .limit(1)
    )
    with source_engine().connect() as conn:
        row = conn.execute(statement).mappings().first()
    if row is None:
        return None
    cpi_text = sanitize_detail(row["texto_cpi"])
    if cpi_text is not None and not isinstance(cpi_text, str):
        cpi_text = json.dumps(cpi_text, ensure_ascii=False, indent=2)
    return {"texto_mpl_id": row["texto_mpl_id"], "texto_legible": row["texto_legible"], "texto_cpi": cpi_text}


def search(start: datetime | None, end: datetime | None, pi_id: str | None = None, limit: int = 50, offset: int = 0, include_all: bool = False, query: str = "", count_total: bool = True, bp: str = "", record_id: str = "", surrogate: str = "", id_banner: str = "", error_http: str = "", bldat: str = "", bp_id: str = "", dni: str = "", mpl_id: str = "", force_count: bool = False) -> dict:
    if pi_id is not None and pi_id not in SUPPORTED_PI:
        raise ValueError("pi_id no admitido")
    t = table("iislog", "iis_run")
    if t is None:
        return {"source_available": False, "items": [], "total": None, "has_next": False}
    json_status, http_status, failed_count, mismatch = _fields(t)
    clauses = [t.c.queue_name == RESULT_QUEUE, t.c.pi_id.in_(SUPPORTED_PI)]
    if start is not None:
        clauses.append(t.c.ts >= start)
    if end is not None:
        clauses.append(t.c.ts < end)
    if not include_all:
        clauses.append(mismatch)
    if pi_id:
        clauses.append(t.c.pi_id == pi_id)
    result_item = t.c.summary_json["json_exec"]["payload"]["data"][0]
    inline = t.c.summary_json["payload"]
    inline_data = inline["data"]
    bp_value = func.coalesce(result_item["KUNNR"].astext, result_item["PARTNER"].astext, inline["KUNNR"].astext, inline["PARTNER"].astext)
    document_date = func.coalesce(result_item["BLDAT"].astext, inline_data["BLDAT"].astext, inline_data[0]["BLDAT"].astext, inline["BLDAT"].astext)
    if bp:
        clauses.append(bp_value == bp)
    if pi_id == "00021":
        if bp_id:
            clauses.append(or_(cast(t.c.run_id, String) == bp_id, result_item["BPEXT"].astext == bp_id, result_item["KUNNR"].astext == bp_id))
        if dni:
            clauses.append(result_item["TAXNUM"].astext == dni)
        if mpl_id:
            mpl_table = table("iislog", "iis_mpl_id")
            pattern = "%" + mpl_id.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            source_match = t.c.summary_json["failed_items"][0]["body"].astext.ilike(pattern, escape="\\")
            if mpl_table is not None:
                stored_match = select(1).select_from(mpl_table).where(
                    mpl_table.c.run_id == t.c.run_id,
                    mpl_table.c.texto_mpl_id.ilike(pattern, escape="\\"),
                ).exists()
                clauses.append(or_(stored_match, source_match))
            else:
                clauses.append(source_match)
    if record_id:
        clauses.append(or_(cast(t.c.run_id, String) == record_id, result_item["VBELN"].astext == record_id, result_item["SalesOrder"].astext == record_id, result_item["AccountingDocument"].astext == record_id, inline["VBELN"].astext == record_id))
    if surrogate:
        clauses.append(or_(and_(t.c.pi_id == "00022", or_(result_item["BSTKD"].astext == surrogate, inline["BSTKD"].astext == surrogate)), and_(t.c.pi_id == "00023", or_(result_item["BSTKD"].astext == surrogate, inline["BSTKD"].astext == surrogate))))
    if id_banner:
        clauses.append(result_item["PARTNER"].astext == id_banner)
    if error_http:
        clauses.append(t.c.summary_json["failed_items"][0]["status_code"].astext == error_http)
    if bldat:
        clauses.append(func.replace(document_date, "-", "") == bldat.replace("-", ""))
    query = query.strip()[:100]
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        searchable = (
            cast(t.c.run_id, String), t.c.pi_id, t.c.status,
            json_status, http_status,
            result_item["BPEXT"].astext, result_item["TAXNUM"].astext, result_item["NAME_LAST"].astext,
            t.c.summary_json["failed_items"][0]["body"].astext,
            t.c.summary_json["failed_items"][0]["status_code"].astext,
            func.to_char(func.timezone("America/Lima", t.c.ts), "DD/MM/YYYY HH24:MI:SS"),
        )
        clauses.append(or_(*(field.ilike(pattern, escape="\\") for field in searchable)))
    page_limit = min(max(limit, 1), 200)
    skip_count = not count_total or (query and start is None and end is None and not force_count)
    statement = select(
        t.c.ts, t.c.run_id, t.c.pi_id, t.c.status, t.c.error_count,
        json_status.label("json_status"), http_status.label("http_status"),
        failed_count.label("failed_items_count"),
        t.c.summary_json["failed_items"].label("failed_items"),
        t.c.summary_json["failed_items"][0]["body"].astext.label("error_body"),
        t.c.summary_json["failed_items"][0]["status_code"].astext.label("failed_http_status"),
        result_item["BPEXT"].astext.label("ib_banner"), result_item["KUNNR"].astext.label("banner_00022"),
        result_item["PARTNER"].astext.label("banner_00023"),
        bp_value.label("bp"),
        func.coalesce(result_item["BSTKD"].astext, inline["BSTKD"].astext).label("surrogate"),
        result_item["ITEMS"].label("result_items"), func.coalesce(inline_data["ITEMS"], inline_data[0]["ITEMS"], inline["ITEMS"]).label("inline_items"),
        result_item["ITEMS"][0]["ZVALORTOTAL"].astext.label("total_amount"),
        result_item["AUDAT"].astext.label("fecha_audat"),
        document_date.label("document_date"),
        func.coalesce(result_item["WRBTR"].astext, inline_data["WRBTR"].astext, inline_data[0]["WRBTR"].astext, inline["WRBTR"].astext).label("payment_amount"),
        func.coalesce(result_item["HKONT"].astext, inline_data["HKONT"].astext, inline_data[0]["HKONT"].astext, inline["HKONT"].astext).label("account"),
        result_item["TAXNUM"].astext.label("dni"),
        result_item["NAME_LAST"].astext.label("apellidos"),
    ).where(*clauses).order_by(t.c.ts.desc()).limit(page_limit + 1 if skip_count else page_limit).offset(max(offset, 0))
    count = select(func.count()).select_from(t).where(*clauses)
    with source_engine().connect() as conn:
        total = None if skip_count else conn.scalar(count) or 0
        rows = list(conn.execute(statement).mappings())
        has_next = len(rows) > page_limit if skip_count else offset + page_limit < total
        mpl_run_ids = {row["run_id"] for row in rows[:page_limit] if row["pi_id"] == "00021" or (row["pi_id"] in {"00022", "00023"} and str(row["status"] or "").upper() == "ERROR")}
        mpl_texts = {}
        mpl_messages = {}
        if mpl_run_ids:
            mpl_table = table("iislog", "iis_mpl_id")
            if mpl_table is not None:
                mpl_rows = conn.execute(
                    select(mpl_table.c.run_id, mpl_table.c.texto_mpl_id, mpl_table.c.texto_legible)
                    .where(mpl_table.c.run_id.in_(mpl_run_ids))
                    .order_by(mpl_table.c.ts.desc())
                ).mappings()
                for mpl_row in mpl_rows:
                    mpl_texts.setdefault(mpl_row["run_id"], mpl_row)
                    if mpl_row["texto_legible"] and str(mpl_row["texto_legible"]).strip():
                        mpl_messages.setdefault(mpl_row["run_id"], mpl_row["texto_legible"])
        items = []
        for row in rows[:page_limit]:
            failed_items = row["failed_items"] if isinstance(row["failed_items"], list) else []
            first_failure = next((item for item in failed_items if isinstance(item, dict)), {})
            error_body = str(first_failure.get("body") or first_failure.get("error") or "")
            error_messages = dict.fromkeys(str(item.get("body")) for item in failed_items if isinstance(item, dict) and item.get("body"))
            classification = None if row["pi_id"] == "00021" and not row["failed_items_count"] else classify_status(row["status"], row["json_status"], row["http_status"], row["failed_items_count"], row["error_count"], first_failure.get("status_code"))
            if row["pi_id"] == "00021" and row["failed_items_count"]:
                classification["kind"] = "BP falló en SAP"
                classification["explanation"] = "El bus completó la operación, pero failed_items registra el rechazo del BP." if str(row["http_status"]) == "200" else "failed_items registra el rechazo del BP."
            if classification is None:
                classification = {"kind": "Sin incidencia", "severity": "normal", "explanation": "Sin errores en los campos evaluados."}
            mpl_row = mpl_texts.get(row["run_id"])
            items.append({"run_ts": sanitize(row["ts"]), "run_id": str(row["run_id"]), "pi_id": row["pi_id"], "status": row["status"], "json_status": row["json_status"], "http_status": row["failed_http_status"] if row["pi_id"] == "00023" else row["http_status"], "error_count": row["error_count"], "failed_items_count": row["failed_items_count"], "failed_status_code": first_failure.get("status_code"), "failed_body": sanitize(str(row["error_body"] or "")[:2000] if row["pi_id"] == "00022" else "; ".join(error_messages)[:2000] if error_messages else error_body[:2000]), "payment_message": sanitize(payment_messages(failed_items)), "mpl_id": extract_mpl_id(error_body) if row["pi_id"] == "00021" else None, "texto_mpl_id": sanitize(bp_mpl_text(mpl_row, error_body)) if row["pi_id"] == "00021" else None, "texto_legible": sanitize(mpl_row["texto_legible"]) if mpl_row else None, "ib_banner": row["banner_00023"] if row["pi_id"] == "00023" else row["banner_00022"] if row["pi_id"] == "00022" else row["ib_banner"] if row["pi_id"] == "00021" else None, "bp": row["bp"], "surrogate": row["surrogate"], "matnr": material_numbers(row["result_items"]) or material_numbers(row["inline_items"]), "total_amount": row["total_amount"], "fecha_audat": row["fecha_audat"], "document_date": row["document_date"], "payment_amount": row["payment_amount"], "account": row["account"], "dni": row["dni"] if row["pi_id"] == "00021" else None, "apellidos": row["apellidos"] if row["pi_id"] == "00021" else None, **classification})
            if row["pi_id"] in {"00022", "00023"} and str(row["status"] or "").upper() == "ERROR":
                readable_text = mpl_messages.get(row["run_id"])
                if not readable_text and mpl_row and mpl_row["texto_mpl_id"]:
                    readable_text = f"Texto legible aún no disponible (MPL-ID: {mpl_row['texto_mpl_id']})"
                items[-1]["sap_error_message"] = sanitize(readable_text)
            else:
                items[-1]["sap_error_message"] = None
    return {"source_available": True, "items": items, "total": total, "has_next": has_next}


def count_by_severity(start: datetime, end: datetime) -> dict:
    t = table("iislog", "iis_run")
    if t is None:
        return {"total": None, "critical": 0, "high": 0}
    json_status, http_status, _, mismatch = _fields(t)
    critical = or_(
        and_(t.c.pi_id != "00021", func.upper(t.c.status).in_(SUCCESS), or_(func.upper(json_status).in_(FAILURE), json_status.like("4%"), json_status.like("5%"), http_status.like("4%"), http_status.like("5%"))),
        t.c.summary_json["failed_items"][0]["status_code"].astext.like("5%"),
    )
    clauses = [t.c.ts >= start, t.c.ts < end, t.c.queue_name == RESULT_QUEUE, t.c.pi_id.in_(SUPPORTED_PI), mismatch]
    statement = select(func.count(), func.coalesce(func.sum(case((critical, 1), else_=0)), 0)).select_from(t).where(*clauses)
    with source_engine().connect() as conn:
        total, critical_count = conn.execute(statement).one()
    return {"total": total, "critical": critical_count, "high": total - critical_count}


def find_sent_payload(run_ts: datetime, run_id: str, detail: bool = False) -> dict | None:
    """Match the closest prior inline message by process-specific business key."""
    t = table("iislog", "iis_run")
    if t is None:
        return None
    with source_engine().connect() as conn:
        result = conn.execute(select(t.c.pi_id, t.c.summary_json).where(t.c.ts == run_ts, t.c.run_id == coerce_filter_value(t.c.run_id, run_id), t.c.queue_name == RESULT_QUEUE).limit(1)).mappings().first()
        if not result or result["pi_id"] not in SUPPORTED_PI:
            return None
        summary = result["summary_json"] or {}
        data = (((summary.get("json_exec") or {}).get("payload") or {}).get("data") or [])
        item = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        key_name = {"00021": "TAXNUM", "00022": "BSTKD", "00023": "ZVIAPAG"}[result["pi_id"]]
        key_value = item.get(key_name)
        if not key_value:
            return None
        inline_payload = t.c.summary_json["payload"]
        expression = inline_payload["data"]["person"]["wnrodoc"].astext if result["pi_id"] == "00021" else inline_payload[key_name].astext
        statement = select(t.c.ts, t.c.run_id, t.c.summary_json).where(t.c.ts >= run_ts - timedelta(days=1), t.c.ts <= run_ts, t.c.pi_id == result["pi_id"], t.c.queue_name == INLINE_QUEUE, expression == str(key_value)).order_by(t.c.ts.desc()).limit(1)
        matched = conn.execute(statement).mappings().first()
        if not matched:
            return None
        formatter = sanitize_detail if detail else sanitize
        return {"run_ts": formatter(matched["ts"]), "run_id": str(matched["run_id"]), "payload": formatter((matched["summary_json"] or {}).get("payload")), "match": "clave de negocio y ejecución anterior más cercana"}
