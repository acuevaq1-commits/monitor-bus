from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class IntegrationEvent:
    ts: datetime
    run_id: str | None
    level: str
    message: str
    corr_id: str | None = None
