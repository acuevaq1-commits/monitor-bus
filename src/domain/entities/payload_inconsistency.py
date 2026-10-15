from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PayloadInconsistency:
    pi_id: str
    path: str
    rule: str
    message: str
    severity: str
    value: Any = None
