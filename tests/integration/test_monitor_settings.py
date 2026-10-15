from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.application.use_cases.manage_settings import save_setting
from src.infrastructure.database.models.monitor import Base, MonitorAudit


def test_threshold_change_is_audited(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'monitor.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = save_setting(session, "thresholds", {"pi_id": "00021", "started_minutes": 15}, "analyst")
        assert row["started_minutes"] == 15
        updated = save_setting(session, "thresholds", {"started_minutes": 20}, "analyst", row["id"])
        assert updated["started_minutes"] == 20
        actions = list(session.scalars(select(MonitorAudit).order_by(MonitorAudit.id)))
        assert [action.action for action in actions] == ["create", "update"]
        assert actions[1].before_json["started_minutes"] == 15
