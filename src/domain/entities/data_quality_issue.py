from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class DataQualityIssue:
    ts: datetime
    run_id: str | None
    field: str
    message: str
    severity: str = "media"
