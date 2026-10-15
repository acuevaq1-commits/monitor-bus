from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine

from src.infrastructure.database.repositories import source


def test_summary_groups_status_rows(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    runs = Table("runs", MetaData(), Column("ts", DateTime(timezone=True)), Column("status", String), Column("pi_id", String))
    runs.create(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(runs.insert(), [{"ts": now - timedelta(minutes=40), "status": "STARTED", "pi_id": "00021"}, {"ts": now - timedelta(minutes=5), "status": "SUCCESS", "pi_id": "00021"}])
    monkeypatch.setattr(source, "table", lambda schema, name: runs)
    monkeypatch.setattr(source, "source_engine", lambda: engine)
    summary = source.SourceRepository("iislog", "iis_run").summary(now - timedelta(hours=1), now)
    assert summary["total"] == 2
    assert summary["statuses"] == {"STARTED": 1, "SUCCESS": 1}
    assert summary["stuck"] == 1
