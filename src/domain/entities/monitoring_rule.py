from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MonitoringRule:
    code: str
    name: str
    category: str
    evaluator: str
    severity: str = "alta"
    pi_id: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    active: bool = True
