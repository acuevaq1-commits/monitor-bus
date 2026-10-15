"""Read-only access to existing logging tables, with reflected column names."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import re
from zoneinfo import ZoneInfo
from sqlalchemy import MetaData, Table, and_, func, select

from src.infrastructure.database.session import source_engine


LIST_OMIT = {"summary_json", "context", "extra", "payload", "payload_json", "request_json", "response_json"}
SENSITIVE = ("password", "token", "secret", "authorization", "cookie", "document", "email", "correo", "dni", "taxnum", "stcdt", "wnrodoc", "wpidm", "wbannerid", "smtp_addr", "tel_number", "name_first", "name_last", "wnamefirst", "wnamelast", "street", "phone", "wtel")
DETAIL_CREDENTIAL_KEYS = {"user", "usuario", "username", "usuarioacceso", "clientid", "password", "passwd", "pwd", "contrasena", "claveacceso", "secret", "clientsecret", "token", "accesstoken", "refreshtoken", "authtoken", "authorization", "apikey", "cookie", "setcookie"}


def sanitize(value, key=""):
    if any(part in key.lower() for part in SENSITIVE):
        return "••••"
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v, key) for v in value[:100]]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo("America/Lima")).isoformat()
    if isinstance(value, str):
        value = value[:262144] + ("… [truncado]" if len(value) > 262144 else "")
        if value.startswith(("{", "[")):
            try:
                return sanitize(json.loads(value), key)
            except (json.JSONDecodeError, RecursionError):
                pass
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "••••", value)
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+", r"\1••••", value)
        return value
    return value


def sanitize_detail(value, key=""):
    """Keep source values in detail views while hiding credential fields."""
    normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
    if normalized_key in DETAIL_CREDENTIAL_KEYS:
        return "****"
    if isinstance(value, dict):
        return {str(k): sanitize_detail(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_detail(item, key) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                return sanitize_detail(json.loads(value), key)
            except (json.JSONDecodeError, RecursionError):
                pass
        return re.sub(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/-]+=*", r"\1 ****", value)
    return value


def coerce_filter_value(column, value):
    """HTTP path values arrive as strings; source keys may be BIGINT."""
    try:
        if column.type.python_type is int:
            return int(value)
    except (AttributeError, NotImplementedError, TypeError, ValueError):
        pass
    return value


@lru_cache
def table(schema: str, name: str):
    engine = source_engine()
    if engine is None:
        return None
    return Table(name, MetaData(), schema=schema, autoload_with=engine)


class SourceRepository:
    def __init__(self, schema: str, name: str):
        self.schema, self.name = schema, name

    @property
    def source_available(self):
        return source_engine() is not None

    def search(self, start: datetime, end: datetime, filters: dict | None = None, limit: int = 50, offset: int = 0, detail: bool = False):
        t = table(self.schema, self.name)
        if t is None:
            return [], 0
        if "ts" not in t.c:
            raise ValueError(f"{self.schema}.{self.name} requiere columna ts")
        clauses = [t.c.ts >= start, t.c.ts < end]
        for key, value in (filters or {}).items():
            if value is not None and value != "" and key in t.c and key not in LIST_OMIT:
                clauses.append(t.c[key] == coerce_filter_value(t.c[key], value))
        cols = list(t.c) if detail else [c for c in t.c if c.name not in LIST_OMIT]
        stmt = select(*cols).where(and_(*clauses)).order_by(t.c.ts.desc()).limit(min(max(limit, 1), 200)).offset(max(offset, 0))
        count = select(func.count()).select_from(t).where(and_(*clauses))
        with source_engine().connect() as conn:
            formatter = sanitize_detail if detail else sanitize
            return [formatter(dict(r)) for r in conn.execute(stmt).mappings()], conn.scalar(count) or 0

    def summary(self, start: datetime, end: datetime, filters: dict | None = None):
        t = table(self.schema, self.name)
        if t is None:
            return None
        clauses = [t.c.ts >= start, t.c.ts < end]
        for key, value in (filters or {}).items():
            if value is not None and value != "" and key in t.c and key not in LIST_OMIT:
                clauses.append(t.c[key] == coerce_filter_value(t.c[key], value))
        with source_engine().connect() as conn:
            total = conn.scalar(select(func.count()).select_from(t).where(*clauses)) or 0
            statuses = {row[0]: row[1] for row in conn.execute(select(t.c.status, func.count()).where(*clauses).group_by(t.c.status))} if "status" in t.c else {}
            integrations = conn.scalar(select(func.count(func.distinct(t.c.pi_id))).where(*clauses)) if "pi_id" in t.c else None
            stuck = conn.scalar(select(func.count()).select_from(t).where(*clauses, t.c.status == "STARTED", t.c.ts < end - timedelta(minutes=30))) if "status" in t.c else None
            return {"total": total, "statuses": {str(k or "SIN ESTADO").upper(): v for k, v in statuses.items()}, "integrations": integrations, "stuck": stuck}

    def latest_within(self, start: datetime | None, end: datetime | None, filters: dict | None = None):
        t = table(self.schema, self.name)
        if t is None:
            return None
        columns = [t.c.ts]
        for name in ("run_id", "pi_id", "status"):
            if name in t.c:
                columns.append(t.c[name])
        clauses = []
        if start is not None:
            clauses.append(t.c.ts >= start)
        if end is not None:
            clauses.append(t.c.ts < end)
        for key, value in (filters or {}).items():
            if value is not None and value != "" and key in t.c and key not in LIST_OMIT:
                clauses.append(t.c[key] == coerce_filter_value(t.c[key], value))
        statement = select(*columns).where(*clauses).order_by(t.c.ts.desc()).limit(1)
        with source_engine().connect() as conn:
            row = conn.execute(statement).mappings().first()
            return sanitize(dict(row)) if row else None

    def get_run(self, ts: datetime, run_id: str, detail: bool = False):
        t = table("iislog", "iis_run")
        if t is None:
            return None
        with source_engine().connect() as conn:
            row = conn.execute(select(t).where(t.c.ts == ts, t.c.run_id == coerce_filter_value(t.c.run_id, run_id)).limit(1)).mappings().first()
            return (sanitize_detail if detail else sanitize)(dict(row)) if row else None

    def templates(self, limit: int = 100):
        t = table("iisupao", "plantilla_integracion")
        if t is None:
            return []
        cols = [c for c in t.c if c.name not in LIST_OMIT]
        with source_engine().connect() as conn:
            statement = select(*cols).where(t.c.pi_id.in_(("00021", "00022", "00023"))).order_by(t.c.pi_id).limit(min(limit, 3))
            return [sanitize(dict(r)) for r in conn.execute(statement).mappings()]


runs = SourceRepository("iislog", "iis_run")
events = SourceRepository("iislog", "iis_event")
dq_issues = SourceRepository("iislog", "dq_issue")
