from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from src.infrastructure.database.queries import failed_attempts


def test_failed_attempts_queries_group_by_lima_day_banner_and_mpl_message(monkeypatch):
    metadata = MetaData()
    source = Table("iis_run", metadata, Column("ts", DateTime), Column("run_id", BigInteger), Column("pi_id", String), Column("status", String), Column("queue_name", String), Column("summary_json", JSONB), schema="iislog")
    mpl = Table("iis_mpl_id", metadata, Column("ts", DateTime), Column("run_id", BigInteger), Column("texto_legible", Text), schema="iislog")
    statements = []

    class Result:
        def mappings(self):
            return []

    class Connection:
        def execution_options(self, **kwargs):
            return self

        def execute(self, statement):
            statements.append(statement)
            return Result()

    class Engine:
        @contextmanager
        def connect(self):
            yield Connection()

    monkeypatch.setattr(failed_attempts, "table", lambda _, name: source if name == "iis_run" else mpl)
    monkeypatch.setattr(failed_attempts, "source_engine", Engine)
    cards = failed_attempts.summary()
    assert all(card["attempts"] == 0 for card in cards.values())
    assert failed_attempts.detail("00021", min_attempts=5)["items"] == []
    assert failed_attempts.detail("00022", min_attempts=5)["items"] == []
    start = datetime(2026, 10, 14, 5, tzinfo=timezone.utc)
    end = datetime(2026, 10, 15, 5, tzinfo=timezone.utc)
    failed_attempts.summary(start, end)
    assert list(failed_attempts.export_rows("00022", min_attempts=5, start=start, end=end)) == []
    summary_params = list(statements[0].compile(dialect=postgresql.dialect()).params.values())
    assert "BPEXT" in summary_params and "KUNNR" in summary_params and "PARTNER" in summary_params
    assert "ERROR" in str(summary_params) and "4%" in summary_params and "5%" in summary_params
    cargo = statements[2].compile(dialect=postgresql.dialect())
    cargo_sql = str(cargo)
    assert "LEFT OUTER JOIN iislog.iis_mpl_id" in cargo_sql
    assert "iis_mpl_id.texto_legible" in cargo_sql
    assert "iis_run.ts = iislog.iis_mpl_id.ts" in cargo_sql and "iis_run.run_id = iislog.iis_mpl_id.run_id" in cargo_sql
    assert "timezone" in cargo_sql and "PARTITION BY" in cargo_sql
    assert "fecha_error" in cargo_sql and "total_por_identificador" in cargo_sql
    assert "array_agg" in cargo_sql and "run_ts" in cargo_sql and "run_id" in cargo_sql
    assert "sum(" in cargo_sql and ">=" in cargo_sql
    assert 5 in cargo.params.values()
    assert start in statements[3].compile(dialect=postgresql.dialect()).params.values()
    assert start in statements[4].compile(dialect=postgresql.dialect()).params.values()
    assert end in statements[4].compile(dialect=postgresql.dialect()).params.values()
    assert "LIMIT" not in str(statements[4].compile(dialect=postgresql.dialect()))


def test_failed_attempts_rejects_other_integrations():
    try:
        failed_attempts.detail("00024")
    except ValueError as exc:
        assert "no admitida" in str(exc)
    else:
        raise AssertionError("00024 no debe tener detalle de intentos")
