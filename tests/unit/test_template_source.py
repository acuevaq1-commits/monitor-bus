from contextlib import contextmanager

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from src.infrastructure.database.repositories import source


def test_templates_only_query_supported_integrations(monkeypatch):
    table = Table("plantilla_integracion", MetaData(), Column("pi_id", String), Column("pi_metadata", JSONB), schema="iisupao")
    statements = []

    class Result:
        def mappings(self):
            return []

    class Connection:
        def execute(self, statement):
            statements.append(statement)
            return Result()

    class Engine:
        @contextmanager
        def connect(self):
            yield Connection()

    monkeypatch.setattr(source, "table", lambda *_: table)
    monkeypatch.setattr(source, "source_engine", Engine)
    assert source.SourceRepository("iisupao", "plantilla_integracion").templates() == []
    statement = statements[0]
    params = statement.compile(dialect=postgresql.dialect()).params
    assert ["00021", "00022", "00023"] in params.values()
    assert statement.selected_columns.keys() == ["pi_id", "pi_metadata"]
