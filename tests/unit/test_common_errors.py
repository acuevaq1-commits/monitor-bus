from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, MetaData, Table, Text
from sqlalchemy.dialects import postgresql

from src.infrastructure.database.queries import common_errors


def test_common_errors_filters_dates_and_pages(monkeypatch):
    mpl = Table("iis_mpl_id", MetaData(), Column("ts", DateTime), Column("run_id", BigInteger),
                Column("texto_legible", Text), schema="iislog")
    statements = []

    class Result:
        def mappings(self):
            return [{"ts": datetime(2026, 10, 8, 15, tzinfo=timezone.utc), "run_id": 99,
                     "texto_legible": "Pedido rechazado"}]

    class Connection:
        def execute(self, statement):
            statements.append(statement)
            return Result()

    class Engine:
        @contextmanager
        def connect(self):
            yield Connection()

    monkeypatch.setattr(common_errors, "table", lambda *args: mpl)
    monkeypatch.setattr(common_errors, "source_engine", Engine)
    start = datetime(2026, 10, 8, 5, tzinfo=timezone.utc)
    end = datetime(2026, 10, 9, 5, tzinfo=timezone.utc)
    result = common_errors.search(start, end, page=2)
    assert result["items"][0]["message"] == "Pedido rechazado"
    assert not result["has_next"]
    compiled = statements[0].compile(dialect=postgresql.dialect())
    assert "iis_mpl_id.ts >= " in str(compiled) and "iis_mpl_id.ts < " in str(compiled)
    assert "btrim(iislog.iis_mpl_id.texto_legible)" in str(compiled)
    assert start in compiled.params.values() and end in compiled.params.values()
    assert 50 in compiled.params.values()
