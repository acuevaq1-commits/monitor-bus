from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class IntegrationRun:
    ts: datetime
    run_id: str
    pi_id: str = ""
    status: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    total: int | None = None
    executed: int | None = None
    ok_count: int | None = None
    error_count: int | None = None
    corr_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
