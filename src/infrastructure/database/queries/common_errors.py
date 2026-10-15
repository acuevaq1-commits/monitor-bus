"""Readable CPI/SAP errors recorded in iis_mpl_id."""
from datetime import datetime

from sqlalchemy import func, select

from src.infrastructure.database.repositories.source import sanitize, source_engine, table


PAGE_SIZE = 50


def search(start: datetime, end: datetime, page: int = 1):
    mpl = table("iislog", "iis_mpl_id")
    if mpl is None:
        return {"source_available": False, "items": [], "has_next": False}

    statement = (select(mpl.c.ts, mpl.c.run_id, mpl.c.texto_legible)
                 .where(mpl.c.ts >= start, mpl.c.ts < end,
                        mpl.c.texto_legible.is_not(None), func.btrim(mpl.c.texto_legible) != "")
                 .order_by(mpl.c.ts.desc(), mpl.c.run_id.desc())
                 .limit(PAGE_SIZE + 1).offset((max(page, 1) - 1) * PAGE_SIZE))
    with source_engine().connect() as connection:
        rows = list(connection.execute(statement).mappings())
    return {"source_available": True,
            "items": [{"ts": row["ts"], "run_id": row["run_id"],
                       "message": sanitize(row["texto_legible"])} for row in rows[:PAGE_SIZE]],
            "has_next": len(rows) > PAGE_SIZE}
