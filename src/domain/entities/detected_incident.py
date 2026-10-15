from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class DetectedIncident:
    category: str
    severity: str
    title: str
    detected_at: datetime
    pi_id: str | None = None
    run_id: str | None = None
    run_ts: datetime | None = None
    corr_id: str | None = None
    business_key: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
