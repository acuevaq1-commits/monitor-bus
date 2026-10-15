from typing import Protocol
from src.domain.entities.detected_incident import DetectedIncident


class Notifier(Protocol):
    def send(self, incident: DetectedIncident) -> None: ...
