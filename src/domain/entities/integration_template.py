from dataclasses import dataclass


@dataclass(slots=True)
class IntegrationTemplate:
    pi_id: str
    name: str
    active: bool = True
    queue_name: str | None = None
