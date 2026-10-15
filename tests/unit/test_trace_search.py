from contextlib import contextmanager

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from src.infrastructure.database.queries import trace_search


def test_trace_identifier_mappings(monkeypatch):
    source = Table(
        "iis_run", MetaData(),
        Column("ts", DateTime), Column("run_id", Integer), Column("corr_id", String),
        Column("queue_name", String), Column("status", String), Column("error_count", Integer),
        Column("ticket_id", Integer), Column("pi_id", String), Column("summary_json", JSONB),
        schema="iislog",
    )
    captured = []

    class Result:
        def mappings(self):
            return []

    class Connection:
        def execute(self, statement):
            captured.append(statement)
            return Result()

    class Engine:
        @contextmanager
        def connect(self):
            yield Connection()

    monkeypatch.setattr(trace_search, "source_engine", Engine)
    monkeypatch.setattr(trace_search, "table", lambda *_: source)

    trace_search.search("cargos", {"id_banner": "BANNER", "surrogate": "SURROGATE"})
    statement = captured[0]
    params = statement.compile(dialect=postgresql.dialect()).params
    assert "$.**.KUNNR ? (@ == $needle)" in params.values()
    assert "$.**.BSTKD ? (@ == $needle)" in params.values()
    assert "$.** ? (@ == $needle)" not in params.values()

    banner = statement.selected_columns["id_banner"].compile(dialect=postgresql.dialect()).params
    surrogate = statement.selected_columns["surrogate"].compile(dialect=postgresql.dialect()).params
    assert "KUNNR" in banner.values() and "BSTKD" not in banner.values()
    assert "BSTKD" in surrogate.values() and "KUNNR" not in surrogate.values()

    trace_search.search("bp", {"dni": "DOCUMENTO", "surrogate": "IGNORADO"})
    bp_statement = captured[1]
    bp_params = bp_statement.compile(dialect=postgresql.dialect()).params
    assert "$.**.TAXNUM ? (@ == $needle)" in bp_params.values()
    assert "$.**.wnrodoc ? (@ == $needle)" in bp_params.values()
    assert "$.** ? (@ == $needle)" not in bp_params.values()
    dni = bp_statement.selected_columns["dni"].compile(dialect=postgresql.dialect()).params
    assert "TAXNUM" in dni.values() and "wnrodoc" in dni.values()

    trace_search.search("pagos", {"id_banner": "PARTNER-23", "surrogate": "BSTKD-23"})
    payment_statement = captured[2]
    payment_params = payment_statement.compile(dialect=postgresql.dialect()).params
    assert "$.**.PARTNER ? (@ == $needle)" in payment_params.values()
    assert "$.**.BSTKD ? (@ == $needle)" in payment_params.values()
    payment_banner = payment_statement.selected_columns["id_banner"].compile(dialect=postgresql.dialect()).params
    payment_surrogate = payment_statement.selected_columns["surrogate"].compile(dialect=postgresql.dialect()).params
    assert "PARTNER" in payment_banner.values()
    assert "BSTKD" in payment_surrogate.values() and "SURROGATE" not in payment_surrogate.values()
