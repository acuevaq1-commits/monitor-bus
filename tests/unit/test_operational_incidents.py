from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from src.infrastructure.database.queries import operational_incidents as incidents


def test_operational_cards_count_stuck_sap_and_missing_results(monkeypatch):
    now = datetime(2026, 10, 8, 15, tzinfo=timezone.utc)
    source = Table("iis_run", MetaData(), Column("ts", DateTime(timezone=True)),
                   Column("run_id", String), Column("pi_id", String), Column("status", String),
                   Column("queue_name", String), Column("summary_json", JSONB), schema="iislog")
    statements = []

    class Connection:
        def scalar(self, statement):
            statements.append(statement)
            return len(statements)

        def execute(self, statement):
            statements.append(statement)
            return self

        def mappings(self):
            return [{"pi_id": "00021", "last_ts": now - timedelta(hours=2)},
                    {"pi_id": "00022", "last_ts": now - timedelta(hours=25)}]

    class Engine:
        @contextmanager
        def connect(self):
            yield Connection()

    monkeypatch.setattr(incidents, "table", lambda *_: source)
    monkeypatch.setattr(incidents, "source_engine", Engine)
    cards = incidents.summary(now, inactivity_hours=24)
    assert cards["stuck"]["count"] == 1
    assert cards["sap"]["count"] == 2
    assert cards["inactive"]["count"] == 2
    stuck_sql = str(statements[0].compile(dialect=postgresql.dialect()))
    sap_sql = str(statements[1].compile(dialect=postgresql.dialect()))
    assert "STARTED" in statements[0].compile(dialect=postgresql.dialect()).params.values()
    assert "queue_name" in sap_sql and "jsonb_array_length" in sap_sql
    assert "ts <" in stuck_sql
    inactive = incidents.detail("inactive", now=now, inactivity_hours=24)
    assert [(item["pi_id"], item["hours_without_results"]) for item in inactive["items"]] == [
        ("00022", 25.0), ("00023", None)]
