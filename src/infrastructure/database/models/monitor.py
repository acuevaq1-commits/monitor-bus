from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, MetaData, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.infrastructure.settings import get_settings


schema = None if get_settings().database_url.startswith("sqlite") else "iismonitor"


class Base(DeclarativeBase):
    metadata = MetaData(schema=schema)


class MonitoringRule(Base):
    __tablename__ = "monitoring_rule"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    evaluator: Mapped[str] = mapped_column(String(80))
    pi_id: Mapped[str | None] = mapped_column(String(30))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(20), default="alta")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class MonitoringThreshold(Base):
    __tablename__ = "monitoring_threshold"
    id: Mapped[int] = mapped_column(primary_key=True)
    pi_id: Mapped[str] = mapped_column(String(30), unique=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=600)
    started_minutes: Mapped[int] = mapped_column(Integer, default=30)
    no_activity_minutes: Mapped[int] = mapped_column(Integer, default=60)
    min_success_rate: Mapped[int] = mapped_column(Integer, default=95)
    max_errors: Mapped[int] = mapped_column(Integer, default=0)
    max_dq_percent: Mapped[int] = mapped_column(Integer, default=5)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    max_duplicates: Mapped[int] = mapped_column(Integer, default=0)


class ExecutionWindow(Base):
    __tablename__ = "execution_window"
    id: Mapped[int] = mapped_column(primary_key=True)
    pi_id: Mapped[str] = mapped_column(String(30))
    weekdays: Mapped[list] = mapped_column(JSON, default=list)
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))
    expected_frequency_minutes: Mapped[int] = mapped_column(Integer)
    tolerance_minutes: Mapped[int] = mapped_column(Integer, default=0)
    timezone: Mapped[str] = mapped_column(String(60), default="America/Lima")
    exceptions: Mapped[list] = mapped_column(JSON, default=list)


class PayloadRule(Base):
    __tablename__ = "payload_rule"
    id: Mapped[int] = mapped_column(primary_key=True)
    pi_id: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    json_path: Mapped[str] = mapped_column(String(300))
    validation_type: Mapped[str] = mapped_column(String(40))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="alta")
    stage: Mapped[str] = mapped_column(String(30), default="input")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ErrorCatalog(Base):
    __tablename__ = "error_catalog"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100))
    origin: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DetectedIncident(Base):
    __tablename__ = "detected_incident"
    id: Mapped[int] = mapped_column(primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("monitoring_rule.id"))
    category: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="abierto")
    pi_id: Mapped[str | None] = mapped_column(String(30))
    run_id: Mapped[str | None] = mapped_column(String(100))
    run_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    corr_id: Mapped[str | None] = mapped_column(String(200))
    business_key: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    assigned_to: Mapped[str | None] = mapped_column(String(100))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("category", "run_ts", "run_id", "title", name="uq_incident_source"),)


class IncidentOccurrence(Base):
    __tablename__ = "incident_occurrence"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("detected_incident.id"))
    run_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[str | None] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IncidentAction(Base):
    __tablename__ = "incident_action"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("detected_incident.id"))
    action: Mapped[str] = mapped_column(String(30))
    actor: Mapped[str] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class NotificationChannel(Base):
    __tablename__ = "notification_channel"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(30))
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    min_severity: Mapped[str] = mapped_column(String(20), default="alta")
    schedule: Mapped[dict] = mapped_column(JSON, default=dict)
    templates: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    secret_reference: Mapped[str | None] = mapped_column(String(200))


class NotificationHistory(Base):
    __tablename__ = "notification_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("notification_channel.id"))
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("detected_incident.id"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    result: Mapped[str] = mapped_column(String(30))
    error_summary: Mapped[str | None] = mapped_column(Text)


class MonitorAudit(Base):
    __tablename__ = "monitor_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(30))
    entity: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    before_json: Mapped[dict | None] = mapped_column(JSON)
    after_json: Mapped[dict | None] = mapped_column(JSON)
